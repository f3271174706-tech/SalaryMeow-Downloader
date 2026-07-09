import asyncio
import concurrent.futures
import json
import os
import platform
import re
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import httpx

from douyin_downloader.config import config, get_logger, setup_logging
from douyin_downloader.range_checker import check_range_support, get_optimal_chunk_size

# 初始化日志系统
setup_logging()
logger = get_logger(__name__)


def _playwright_launch_args() -> dict:
    """Return platform-appropriate Playwright launch args."""
    if platform.system() == "Windows":
        return {"channel": "msedge"}
    return {"executable_path": "/snap/bin/chromium", "args": ["--no-sandbox"]}


# 浏览器池 - 复用浏览器实例，避免每次启动
_browser_pool = []
_browser_lock = threading.Lock()
_playwright_instance = None


def _get_browser():
    """获取浏览器实例（复用池中的实例）"""
    global _playwright_instance
    with _browser_lock:
        if _browser_pool:
            browser = _browser_pool.pop()
            # 检查浏览器是否还可用
            try:
                if browser.is_connected():
                    return browser, None
            except Exception:
                pass

        # 需要创建新实例
        from playwright.sync_api import sync_playwright

        if _playwright_instance is None:
            _playwright_instance = sync_playwright().start()
        browser = _playwright_instance.chromium.launch(headless=True, **_playwright_launch_args())
        return browser, _playwright_instance


def _return_browser(browser):
    """归还浏览器实例到池中"""
    with _browser_lock:
        try:
            if browser.is_connected():
                _browser_pool.append(browser)
            else:
                browser.close()
        except Exception:
            pass


DOWNLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "downloads"

# Auto-detect system proxy for httpx (used for Twitter/TikTok)
_system_proxies = urllib.request.getproxies()
PROXY_URL = _system_proxies.get("http") or _system_proxies.get("https")

# Set proxy env vars so httpx picks them up automatically (works with all httpx versions)
if PROXY_URL:
    os.environ.setdefault("HTTP_PROXY", PROXY_URL)
    os.environ.setdefault("HTTPS_PROXY", PROXY_URL)

# Monkey-patch httpx to always use proxy from env vars (for older httpx versions)
_orig_get = httpx.get
_orig_post = httpx.post


def _get(*a, **kw):
    kw.setdefault("trust_env", True)
    return _orig_get(*a, **kw)


def _post(*a, **kw):
    kw.setdefault("trust_env", True)
    return _orig_post(*a, **kw)


httpx.get = _get
httpx.post = _post

# Simple in-memory cache to avoid hitting Douyin repeatedly for the same URL
_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 600  # 10 minutes
_CACHE_MAX_SIZE = 500  # 最大缓存条目数


def _cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["_ts"] < _CACHE_TTL:
            return entry
        if entry:
            del _cache[key]
        return None


def _cache_set(key: str, info: dict):
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX_SIZE:
            oldest_key = min(_cache.keys(), key=lambda k: _cache[k].get("_ts", 0))
            del _cache[oldest_key]
        info["_ts"] = time.time()
        _cache[key] = info


# 共享线程池，避免反复创建
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)


def _ensure_downloads_dir():
    DOWNLOADS_DIR.mkdir(exist_ok=True)


def _extract_url(text: str) -> str:
    """Extract and normalize the first URL from user input (may contain share text)."""
    text = text.strip()
    url_match = re.search(
        r"(https?://\S+|v\.douyin\.com/\S+|vm\.tiktok\.com/\S+|vt\.tiktok\.com/\S+)",
        text,
    )
    if url_match:
        url = url_match.group(1)
        url = url.rstrip(".,;:!?，。；：！？)")
    else:
        url = text

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def _is_douyin(url: str) -> bool:
    return any(d in url for d in ["douyin.com", "iesdouyin.com"])


def _is_twitter(url: str) -> bool:
    return any(d in url for d in ["twitter.com", "x.com"])


def _is_tiktok(url: str) -> bool:
    return "tiktok.com" in url


def _is_bilibili(url: str) -> bool:
    return any(d in url for d in ["bilibili.com", "b23.tv"])


def _is_kuaishou(url: str) -> bool:
    return any(d in url for d in ["kuaishou.com", "v.kuaishou.com", "gifshow.com"])


def _resolve_douyin(url: str) -> tuple[str, str]:
    """Resolve a Douyin short link. Returns (id, type) where type is 'video' or 'note'."""
    # Direct URL patterns — slides also use note endpoint for data
    for pattern, content_type in [(r"/video/(\d+)", "video"), (r"/note/(\d+)", "note"), (r"/slides/(\d+)", "note")]:
        match = re.search(pattern, url)
        if match:
            return match.group(1), content_type

    # Resolve short link (302 redirect)
    headers = {"User-Agent": MOBILE_UA}
    r = httpx.get(url, headers=headers, follow_redirects=False, timeout=30)

    if r.status_code in (301, 302):
        location = r.headers.get("location", "")
        for pattern, content_type in [(r"/video/(\d+)", "video"), (r"/note/(\d+)", "note"), (r"/slides/(\d+)", "note")]:
            match = re.search(pattern, location)
            if match:
                return match.group(1), content_type

    # Follow full redirect chain
    r = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
    final_url = str(r.url)
    for pattern, content_type in [(r"/video/(\d+)", "video"), (r"/note/(\d+)", "note"), (r"/slides/(\d+)", "note")]:
        match = re.search(pattern, final_url)
        if match:
            return match.group(1), content_type

    raise ValueError(f"无法从链接中解析: {url}")


def _extract_images_with_playwright(share_url: str) -> tuple[list[str], list[str]]:
    """Use Playwright to extract video URLs and images from a Douyin note page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], []

    video_urls = []
    images = []

    # 从浏览器池获取实例
    browser, pw = _get_browser()
    page = None
    try:
        page = browser.new_page()
        page.goto(share_url, wait_until="domcontentloaded", timeout=15000)

        # Wait for images to stabilize (lazy-loaded), poll every 400ms, max 5s
        prev_count = 0
        stable_rounds = 0
        for _ in range(13):
            try:
                count = page.evaluate("""() => {
                    let n = 0;
                    document.querySelectorAll('img').forEach(el => {
                        const src = el.src || '';
                        if (src.includes('douyinpic') && src.includes('tos-cn-i-') &&
                            !src.includes('100x100') && !src.includes('avatar')) n++;
                    });
                    return n;
                }""")
            except Exception:
                page.wait_for_timeout(400)
                continue
            if count != prev_count:
                stable_rounds = 0
                prev_count = count
                page.wait_for_timeout(400)
                continue
            stable_rounds += 1
            if count > 0 and stable_rounds >= 4:
                break
            if count == 0 and stable_rounds >= 6:
                break
            page.wait_for_timeout(400)

        # Wait for video elements to appear (they load after images)
        for _ in range(8):
            has_video = page.evaluate("""() => {
                let found = false;
                document.querySelectorAll('video source').forEach(el => {
                    const src = el.src || el.getAttribute('src') || '';
                    if (src.includes('douyinvod')) found = true;
                });
                return found;
            }""")
            if has_video:
                break
            page.wait_for_timeout(400)

        # Batch extract via JS
        all_data = page.evaluate("""() => {
            const videos = [];
            const seenPaths = new Set();
            document.querySelectorAll('video source').forEach(el => {
                const src = el.src || el.getAttribute('src') || '';
                if (!src || !src.includes('douyinvod')) return;
                const pm = src.match(/douyinvod\\.com\\/[^\\/]+\\/[^\\/]+(\\/video\\/[^?]+)/);
                const path = pm ? pm[1] : src;
                if (seenPaths.has(path)) return;
                seenPaths.add(path);
                videos.push(src);
            });
            const images = [];
            const seen = new Set();
            const container = document.querySelector('.note-detail-container');
            const scope = container || document;
            scope.querySelectorAll('img').forEach(el => {
                const src = el.src || '';
                if (!src || !src.includes('douyinpic')) return;
                if (src.includes('100x100') || src.includes('avatar')) return;
                if (src.includes('image-cut-tos-priv')) return;
                if (src.includes('image-cut-tos')) return;
                if (src.includes('ies.fe.effect')) return;
                if (src.includes('sticker')) return;
                if (src.includes('p14lwwcsbr')) return;
                if (!src.includes('tos-cn-i-')) return;
                const w = el.naturalWidth || el.width || 0;
                const h = el.naturalHeight || el.height || 0;
                if (w < 200 || h < 200) return;
                const idMatch = src.match(/tos-cn-i-[^~?]+/);
                const imgId = idMatch ? idMatch[0] : src;
                if (seen.has(imgId)) return;
                seen.add(imgId);
                images.push(src);
            });
            return {videos, images};
        }""")
        video_urls = all_data.get("videos", [])
        images = all_data.get("images", [])

        page.close()
        _return_browser(browser)

    except Exception as e:
        logger.error(f"Playwright 提取失败: {e}", exc_info=True)
        if page:
            try:
                page.close()
            except Exception:
                pass
        _return_browser(browser)
        return [], []

    return video_urls, images


def _extract_with_playwright_async(share_url: str) -> tuple[list[str], list[str]]:
    """Async version of Playwright extraction for use in FastAPI."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return [], []

    async def _extract():
        video_urls = []
        images = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, **_playwright_launch_args())
            page = await browser.new_page()
            await page.goto(share_url, wait_until="domcontentloaded", timeout=15000)

            # Wait for images to stabilize
            prev_count = 0
            stable_rounds = 0
            for _ in range(13):
                try:
                    count = await page.evaluate("""() => {
                        let n = 0;
                        document.querySelectorAll('img').forEach(el => {
                            const src = el.src || '';
                            if (src.includes('douyinpic') && src.includes('tos-cn-i-') &&
                                !src.includes('100x100') && !src.includes('avatar')) n++;
                        });
                        return n;
                    }""")
                except Exception:
                    await page.wait_for_timeout(400)
                    continue
                if count != prev_count:
                    stable_rounds = 0
                    prev_count = count
                    await page.wait_for_timeout(400)
                    continue
                stable_rounds += 1
                if count > 0 and stable_rounds >= 4:
                    break
                if count == 0 and stable_rounds >= 6:
                    break
                await page.wait_for_timeout(400)

            # Wait for video elements
            for _ in range(8):
                has_video = await page.evaluate("""() => {
                    let found = false;
                    document.querySelectorAll('video source').forEach(el => {
                        const src = el.src || el.getAttribute('src') || '';
                        if (src.includes('douyinvod')) found = true;
                    });
                    return found;
                }""")
                if has_video:
                    break
                await page.wait_for_timeout(400)

            # Batch extract
            all_data = await page.evaluate(r"""() => {
                const videos = [];
                const seenPaths = new Set();
                document.querySelectorAll('video source').forEach(el => {
                    const src = el.src || el.getAttribute('src') || '';
                    if (!src || !src.includes('douyinvod')) return;
                    const pm = src.match(/douyinvod\.com\/[^\/]+\/[^\/]+(\/video\/[^?]+)/);
                    const path = pm ? pm[1] : src;
                    if (seenPaths.has(path)) return;
                    seenPaths.add(path);
                    videos.push(src);
                });
                const images = [];
                const seen = new Set();
                const container = document.querySelector('.note-detail-container');
                const scope = container || document;
                scope.querySelectorAll('img').forEach(el => {
                    const src = el.src || '';
                    if (!src || !src.includes('douyinpic')) return;
                    if (src.includes('100x100') || src.includes('avatar')) return;
                    if (src.includes('image-cut-tos-priv')) return;
                    if (src.includes('image-cut-tos')) return;
                    if (src.includes('ies.fe.effect')) return;
                    if (src.includes('sticker')) return;
                    if (src.includes('p14lwwcsbr')) return;
                    if (!src.includes('tos-cn-i-')) return;
                    const w = el.naturalWidth || el.width || 0;
                    const h = el.naturalHeight || el.height || 0;
                    if (w < 200 || h < 200) return;
                    const idMatch = src.match(/tos-cn-i-[^~?]+/);
                    const imgId = idMatch ? idMatch[0] : src;
                    if (seen.has(imgId)) return;
                    seen.add(imgId);
                    images.push(src);
                });
                return {videos, images};
            }""")
            video_urls = all_data.get("videos", [])
            images = all_data.get("images", [])

            await browser.close()

        return video_urls, images

    # Run in a new thread to avoid asyncio conflicts
    future = _thread_pool.submit(asyncio.run, _extract())
    return future.result(timeout=120)


def _safe_decode_json_str(raw: str) -> str:
    """Safely decode a JSON-escaped string."""
    try:
        return json.loads('"' + raw + '"')
    except json.JSONDecodeError:
        pass
    try:
        return raw.encode("utf-8").decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return raw


def _extract_douyin(url: str) -> dict:
    """Extract Douyin video or photo note info by scraping the mobile share page."""
    item_id, content_type = _resolve_douyin(url)
    path_segment = "note" if content_type == "note" else "video"
    share_url = f"https://www.iesdouyin.com/share/{path_segment}/{item_id}/"
    headers = {"User-Agent": MOBILE_UA, "Referer": share_url}

    r = httpx.get(share_url, headers=headers, follow_redirects=True, timeout=30)
    html = r.text

    # Extract title
    title = "未知标题"
    desc_match = re.search(r'"desc":"([^"]{1,300})"', html)
    if desc_match:
        title = _safe_decode_json_str(desc_match.group(1))

    # Extract thumbnail
    thumbnail = ""
    cover_urls = re.findall(r"https:[^\"\s]*douyinpic\.com[^\"\s]*", html)
    for raw in cover_urls:
        decoded = _safe_decode_json_str(raw)
        if "avatar" in decoded or "100x100" in decoded:
            continue
        if not thumbnail or "1080x1080" in decoded:
            thumbnail = decoded
            if "1080x1080" in decoded:
                break

    # Extract background music MP3
    music_url = ""
    music_match = re.search(r'"play_addr":\{"uri":"([^"]+\.mp3)"', html)
    if music_match:
        music_url = _safe_decode_json_str(music_match.group(1))

    if content_type == "note":
        # Extract all images from photo note
        images = []
        img_start = html.find('"images":[')
        if img_start >= 0:
            arr_start = img_start + 9
            depth = 0
            end = arr_start
            for i in range(arr_start, min(arr_start + 500000, len(html))):
                if html[i] == "[":
                    depth += 1
                elif html[i] == "]":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            img_data = html[arr_start:end]
            for block in re.finditer(r'"url_list":\[\"(https?:[^\"]+)"', img_data):
                raw = block.group(1)
                raw = raw.replace("\\u002F", "/")
                img_url = _safe_decode_json_str(raw)
                if "tos-cn-i-" not in img_url:
                    continue
                if img_url not in images:
                    images.append(img_url)

        # Fallback: use Playwright for live photos / animated images
        has_video_hint = '"img_bitrate":null' in html
        if has_video_hint or len(images) == 0 or len(html) < 10000:
            # 优先使用 API 模式解析动图
            if has_video_hint and config.get("api.enabled", True):
                try:
                    from douyin_downloader.douyin_api import _extract_douyin_api

                    logger.info(f"动图帖使用 API 模式: {share_url}")
                    future = _thread_pool.submit(asyncio.run, _extract_douyin_api(share_url))
                    api_result = future.result(timeout=15)
                    if api_result and api_result.get("type") == "live_photo":
                        logger.info(f"API 解析动图成功: {api_result.get('title', '')[:30]}...")
                        return api_result
                    else:
                        logger.warning("API 未返回动图结果，回退到 Playwright")
                except Exception as e:
                    logger.warning(f"API 解析动图失败，回退到 Playwright: {e}")

            # 回退到 Playwright
            logger.info(f"使用 Playwright 解析动图: {share_url}")
            try:
                pw_videos, pw_images = _extract_with_playwright_async(share_url)
                if pw_images:
                    images = pw_images
                if pw_videos:
                    return {
                        "title": title,
                        "thumbnail": images[0] if images else thumbnail,
                        "duration": 0,
                        "type": "live_photo",
                        "video_url": pw_videos[0],
                        "video_urls": pw_videos,
                        "images": images,
                        "music_url": music_url,
                        "platform": "douyin",
                    }
            except Exception as e:
                logger.error(f"Playwright 提取失败: {e}", exc_info=True)

        return {
            "title": title,
            "thumbnail": images[0] if images else thumbnail,
            "duration": 0,
            "type": "photo",
            "images": images,
            "music_url": music_url,
            "platform": "douyin",
        }

    # Video post
    duration = 0
    dur_match = re.search(r'"duration":(\d+)', html)
    if dur_match:
        duration = int(dur_match.group(1))

    video_url = ""
    play_match = re.search(r'"url_list":\["(https?:[^"]+playwm[^"]+)"\]', html)
    if not play_match:
        play_match = re.search(r'"url_list":\["(https?:\\u002F[^"]+playwm[^"]+)"\]', html)
    if play_match:
        wm_url = play_match.group(1)
        wm_url = wm_url.replace("\\u002F", "/")
        try:
            wm_url = _safe_decode_json_str(wm_url)
        except json.JSONDecodeError:
            pass
        video_url = wm_url.replace("/playwm/", "/play/")

    if not video_url:
        uri_match = re.search(r'"uri":"(https?:[^"]+douyinstatic[^"]+)"', html)
        if not uri_match:
            uri_match = re.search(r'"uri":"(https?:\\u002F[^"]+douyinstatic[^"]+)"', html)
        if uri_match:
            video_url = uri_match.group(1)
            video_url = video_url.replace("\\u002F", "/")
            try:
                video_url = _safe_decode_json_str(video_url)
            except json.JSONDecodeError:
                pass

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": duration,
        "type": "video",
        "video_url": video_url,
        "platform": "douyin",
    }


def _extract_tiktok(url: str) -> dict:
    """Extract TikTok video info via ssstiktok.cc + TikTok page for title."""
    # Step 1: 从 TikTok 页面提取标题
    title = "tiktok_video"
    thumbnail = ""
    try:
        r_resolve = httpx.get(
            url, headers={"User-Agent": MOBILE_UA}, follow_redirects=True, timeout=15, proxy="http://127.0.0.1:7890"
        )
        full_url = str(r_resolve.url)

        r_page = httpx.get(
            full_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=30,
            proxy="http://127.0.0.1:7890",
        )

        scripts = re.findall(r"<script[^>]*>(.*?)</script>", r_page.text, re.DOTALL)
        for s in scripts:
            if "playAddr" in s or "play_addr" in s:
                try:
                    data = json.loads(s)
                    item = (
                        data.get("__DEFAULT_SCOPE__", {})
                        .get("webapp.video-detail", {})
                        .get("itemInfo", {})
                        .get("itemStruct", {})
                    )
                    if item:
                        title = item.get("desc", "") or title
                        cover = item.get("video", {}).get("cover", "")
                        if cover:
                            thumbnail = cover
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"TikTok 标题提取失败: {e}")

    # Step 2: 从 ssstiktok.cc 获取下载链接
    r = httpx.post(
        "https://ssstiktok.cc/",
        data={"url": url, "mode": "video"},
        headers={"User-Agent": MOBILE_UA, "Referer": "https://ssstiktok.cc/"},
        follow_redirects=True,
        timeout=30,
    )
    if r.status_code != 200:
        raise ValueError(f"ssstiktok 返回 {r.status_code}")

    preview_match = re.search(r'href="(/preview/[^"]+)"', r.text)
    if not preview_match:
        raise ValueError("ssstiktok 未返回预览链接")

    preview_path = preview_match.group(1)

    r2 = httpx.get(
        f"https://ssstiktok.cc{preview_path}", headers={"User-Agent": MOBILE_UA}, follow_redirects=True, timeout=30
    )
    if r2.status_code != 200:
        raise ValueError(f"ssstiktok 预览页返回 {r2.status_code}")

    dl_match = re.search(r'href="(/download/video/[^"]+)"', r2.text)
    if not dl_match:
        raise ValueError("ssstiktok 未找到下载链接")

    download_url = f"https://ssstiktok.cc{dl_match.group(1)}"

    if title == "tiktok_video":
        title_match = re.search(r"<h2[^>]*>([^<]+)</h2>", r2.text)
        if title_match:
            title = title_match.group(1).strip()

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": 0,
        "type": "video",
        "video_url": download_url,
        "hd_url": download_url,
        "platform": "tiktok",
    }


def _resolve_twitter_url(url: str) -> str:
    """Resolve t.co short links to full Twitter/X URL."""
    if "t.co/" in url:
        r = httpx.get(url, headers={"User-Agent": MOBILE_UA}, follow_redirects=True, timeout=15)
        return str(r.url)
    return url


def _parse_twitter_url(url: str) -> tuple[str, str]:
    """Extract (username, tweet_id) from a Twitter/X URL."""
    url = _resolve_twitter_url(url)
    m = re.search(r"(?:twitter\.com|x\.com)/(\w+)/status/(\d+)", url)
    if not m:
        raise ValueError(f"无法解析推特链接: {url}")
    return m.group(1), m.group(2)


def _curl_get(url: str, timeout: int = 30) -> str:
    """Use subprocess curl to bypass httpx proxy issues on cloud servers."""
    cmd = ["curl", "-s", "-L", "--max-time", str(timeout), "-H", f"User-Agent: {MOBILE_UA}"]
    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    if result.returncode != 0:
        raise ValueError(f"curl failed: {result.stderr[:200]}")
    return result.stdout.decode("utf-8", errors="replace")


def _curl_download(url: str, filepath: str, timeout: int = 120, headers: dict = None, use_proxy: bool = False) -> int:
    """Use subprocess curl to download a file. Returns file size."""
    cmd = ["curl", "-s", "-L", "--max-time", str(timeout), "-o", filepath]
    if use_proxy:
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or "http://127.0.0.1:7890"
        cmd += ["--proxy", proxy]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    if result.returncode != 0:
        raise ValueError(f"curl download failed: {result.stderr[:200]}")
    return os.path.getsize(filepath)


def _extract_twitter(url: str) -> dict:
    """Extract Twitter/X video info via fxtwitter API."""
    username, tweet_id = _parse_twitter_url(url)
    api_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
    text = _curl_get(api_url, timeout=30)
    data = json.loads(text)
    if data.get("code") != 200:
        raise ValueError(data.get("message", "fxtwitter API 错误"))

    tweet = data.get("tweet", {})
    media = tweet.get("media", {})
    all_media = media.get("all", [])

    video_url = ""
    thumbnail = ""
    duration = 0
    variants = []
    for item in all_media:
        if item.get("type") == "video":
            video_url = item.get("url", "")
            thumbnail = item.get("thumbnail_url", "")
            duration = item.get("duration", 0)
            variants = item.get("variants", [])
            break

    if not video_url:
        raise ValueError("该推特不包含视频")

    best_url = video_url
    best_bitrate = 0
    for v in variants:
        if v.get("content_type") == "video/mp4":
            br = v.get("bitrate", 0)
            if br > best_bitrate:
                best_bitrate = br
                best_url = v["url"]
    video_url = best_url

    title = tweet.get("text", "未知标题")[:100]

    m3u8_url = ""
    for v in variants:
        if v.get("content_type") == "application/x-mpegURL":
            m3u8_url = v.get("url", "")
            break

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": duration,
        "type": "video",
        "video_url": video_url,
        "m3u8_url": m3u8_url,
        "platform": "twitter",
    }


def _extract_bilibili(url: str) -> dict:
    """Extract Bilibili video info via API."""
    if "b23.tv" in url:
        r = httpx.get(url, headers={"User-Agent": MOBILE_UA}, follow_redirects=True, timeout=15)
        url = str(r.url)

    bv_match = re.search(r"(BV[\w]+)", url)
    if bv_match:
        bvid = bv_match.group(1)
    else:
        id_match = re.search(r"/video/([\w]+)", url)
        if id_match:
            raw_id = id_match.group(1)
            bvid = raw_id if raw_id.startswith("BV") else "BV" + raw_id
        else:
            raise ValueError(f"无法从链接中提取 BV ID: {url}")

    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.bilibili.com/"}
    bilibili_cookie = config.get_cookie("bilibili")
    if bilibili_cookie:
        headers["Cookie"] = bilibili_cookie

    info_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    r = httpx.get(info_url, headers=headers, timeout=15)
    data = r.json()
    if data.get("code") != 0:
        raise ValueError(data.get("message", "B站 API 错误"))

    video_data = data["data"]
    title = video_data.get("title", "未知标题")
    cid = video_data.get("cid")
    thumbnail = video_data.get("pic", "")
    if thumbnail.startswith("//"):
        thumbnail = "https:" + thumbnail

    play_url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=112&fnval=0"
    r = httpx.get(play_url, headers=headers, timeout=15)
    play_data = r.json()
    if play_data.get("code") != 0:
        raise ValueError(play_data.get("message", "B站播放地址获取失败"))

    durls = play_data["data"].get("durl", [])
    if not durls:
        raise ValueError("B站未返回视频地址")

    video_url = durls[0].get("url", "")

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": video_data.get("duration", 0),
        "type": "video",
        "video_url": video_url,
        "platform": "bilibili",
    }


def _extract_kuaishou(url: str) -> dict:
    """Extract Kuaishou video info by scraping mobile share page."""
    headers = {"User-Agent": MOBILE_UA}
    kuaishou_cookie = config.get_cookie("kuaishou")
    if kuaishou_cookie:
        headers["Cookie"] = kuaishou_cookie
    r = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
    html = r.text
    final_url = str(r.url)

    vid_match = re.search(r"shareObjectId=([^&]+)", final_url)
    if not vid_match:
        vid_match = re.search(r"/short-video/([^?]+)", final_url)
    if not vid_match:
        raise ValueError("无法从快手链接中提取视频 ID")

    mp4_urls = re.findall(r'https://[^"\s]+\.mp4[^"\s]*', html)
    mp4_urls = list(dict.fromkeys(mp4_urls))

    if not mp4_urls:
        raise ValueError("该快手作品不包含视频")

    high_url = ""
    ultra_url = ""
    for u in mp4_urls:
        if "UltraV5" in u and not ultra_url:
            ultra_url = u
        elif "HighV5" in u and not high_url:
            high_url = u

    fallback = mp4_urls[0]
    video_url = high_url or fallback
    hd_url = ultra_url or high_url or fallback

    title = "未知标题"
    title_match = re.search(r'"caption":"([^"]{1,300})"', html)
    if title_match:
        title = title_match.group(1)

    thumbnail = ""
    cover_match = re.search(r'"coverUrl":"([^"]+)"', html)
    if cover_match:
        thumbnail = cover_match.group(1)

    return {
        "title": title,
        "thumbnail": thumbnail,
        "duration": 0,
        "type": "video",
        "video_url": video_url,
        "hd_url": hd_url,
        "platform": "kuaishou",
    }


def apply_quality(video_url: str, quality: str) -> str:
    """Apply quality setting to a Douyin video URL."""
    if "aweme.snssdk.com" not in video_url:
        return video_url
    ratio_map = {"720p": "720p", "1080p": "1080p", "hd": "1080p"}
    ratio = ratio_map.get(quality, "1080p")
    if "ratio=" in video_url:
        return re.sub(r"ratio=\w+", f"ratio={ratio}", video_url)
    return video_url + f"&ratio={ratio}"


def extract_video_info(url: str) -> dict:
    """Extract media metadata. Routes to platform-specific extractors."""
    url = _extract_url(url)
    cached = _cache_get(url)
    if cached:
        logger.debug(f"缓存命中: {url[:50]}...")
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    if _is_douyin(url):
        platform = "douyin"
    elif _is_twitter(url):
        platform = "twitter"
    elif _is_bilibili(url):
        platform = "bilibili"
    elif _is_kuaishou(url):
        platform = "kuaishou"
    elif _is_tiktok(url):
        platform = "tiktok"
    else:
        raise ValueError("不支持的平台链接")

    logger.info(f"解析链接: {url[:50]}... (平台: {platform})")

    info = None
    if config.get("api.enabled", True) and platform == "douyin":
        try:
            from douyin_downloader.douyin_api import _extract_douyin_api

            logger.info(f"尝试使用 API 模式: {platform}")
            future = _thread_pool.submit(asyncio.run, _extract_douyin_api(url))
            info = future.result(timeout=15)
            if info:
                logger.info(f"API 提取成功: {info.get('title', '')[:30]}...")
            else:
                logger.warning("API 返回 None，切换 Cookie 重试")
                config.rotate_cookie(platform)
                future = _thread_pool.submit(asyncio.run, _extract_douyin_api(url))
                info = future.result(timeout=15)
                if info:
                    logger.info("Cookie 切换后 API 提取成功")
                else:
                    logger.warning("Cookie 切换后仍失败，回退到爬虫")
        except Exception as e:
            logger.warning(f"API 提取失败，回退到爬虫: {e}")

    if info is None:
        logger.info(f"使用爬虫模式: {platform}")
        if platform == "douyin":
            info = _extract_douyin(url)
        elif platform == "twitter":
            info = _extract_twitter(url)
        elif platform == "bilibili":
            info = _extract_bilibili(url)
        elif platform == "kuaishou":
            info = _extract_kuaishou(url)
        elif platform == "tiktok":
            info = _extract_tiktok(url)

    if info:
        logger.info(
            f"解析完成: url={url}, platform={platform}, type={info.get('type', 'unknown')}, title={info.get('title', '')[:50]}"
        )

    _cache_set(url, info)
    return {k: v for k, v in info.items() if not k.startswith("_")}


def _convert_to_mp3(video_path: str) -> str:
    """Convert video to MP3 audio using ffmpeg."""
    mp3_path = str(Path(video_path).with_suffix(".mp3"))
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", mp3_path],
        capture_output=True,
        check=True,
    )
    os.remove(video_path)
    return mp3_path


def _make_slides_video(info: dict) -> str:
    """Combine slides images + music into an MP4 video using ffmpeg."""
    images = info.get("images", [])
    music_url = info.get("music_url", "")
    if not images:
        raise ValueError("No images to convert")

    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.iesdouyin.com/"}
    img_count = len(images)

    music_path = None
    image_duration = 3.0
    if music_url:
        r = httpx.get(music_url, headers=headers, follow_redirects=True, timeout=60)
        music_path = str(DOWNLOADS_DIR / f"_slide_a_{uuid.uuid4().hex[:8]}.mp3")
        with open(music_path, "wb") as f:
            f.write(r.content)
        image_duration = 3.0

    vid_paths = []
    for i, img_url in enumerate(images):
        r = httpx.get(img_url, headers=headers, follow_redirects=True, timeout=60)
        img_tmp = str(DOWNLOADS_DIR / f"_slide_img_{uuid.uuid4().hex[:4]}.webp")
        with open(img_tmp, "wb") as f:
            f.write(r.content)
        vid_path = str(DOWNLOADS_DIR / f"_slide_v_{i}_{uuid.uuid4().hex[:4]}.mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                img_tmp,
                "-c:v",
                "libx264",
                "-t",
                f"{image_duration:.2f}",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-vf",
                "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                vid_path,
            ],
            capture_output=True,
            check=True,
        )
        os.remove(img_tmp)
        vid_paths.append(vid_path)

    concat_file = str(DOWNLOADS_DIR / f"_concat_{uuid.uuid4().hex[:4]}.txt")
    with open(concat_file, "w") as f:
        for v in vid_paths:
            f.write(f"file '{v}'\n")

    safe_name = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50] or uuid.uuid4().hex[:12]
    out_path = str(DOWNLOADS_DIR / f"{safe_name}.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file]
    if music_path:
        cmd += ["-i", music_path, "-c:v", "copy", "-c:a", "aac", "-shortest", "-map", "0:v", "-map", "1:a"]
    else:
        cmd += ["-c:v", "copy"]
    cmd.append(out_path)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {result.stderr[:500]}")

    for p in vid_paths:
        try:
            os.remove(p)
        except OSError:
            pass
    if music_path:
        try:
            os.remove(music_path)
        except OSError:
            pass
    try:
        os.remove(concat_file)
    except OSError:
        pass

    _schedule_cleanup(out_path)
    return out_path


def download_video(
    url: str,
    quality: str = "1080p",
    media_type: str = "video",
    image_index: int = 0,
    live_photo_format: bool = False,
    live_photo_index: int = 0,
) -> tuple[str, str]:
    """Download video/image or extract audio. Returns (file_path, filename)."""
    url = _extract_url(url)
    _ensure_downloads_dir()

    if _is_douyin(url):
        info = extract_video_info(url)
        if info["type"] == "photo":
            if media_type == "video" and info.get("music_url"):
                out_path = _make_slides_video(info)
                filename = os.path.basename(out_path)
                return out_path, filename
            elif media_type == "mp3" and info.get("music_url"):
                r = httpx.get(info["music_url"], headers={"User-Agent": MOBILE_UA}, follow_redirects=True, timeout=60)
                safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50]
                filename = f"{safe_title}.mp3" if safe_title else f"{uuid.uuid4().hex[:12]}.mp3"
                filepath = str(DOWNLOADS_DIR / filename)
                with open(filepath, "wb") as f:
                    f.write(r.content)
                _schedule_cleanup(filepath)
                return filepath, filename
            elif len(info.get("images", [])) > 1:
                filepath, filename = _download_single_photo(info, image_index)
            else:
                filepath, filename = _download_single_photo(info, image_index)
        elif info["type"] == "live_photo":
            video_urls = info.get("video_urls", [])
            if live_photo_format:
                images = info.get("images", [])
                if images and video_urls:
                    idx = min(live_photo_index, len(video_urls) - 1, len(images) - 1)
                    img_url = images[idx]
                    vid_url = video_urls[idx]
                    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"}

                    img_r = httpx.get(img_url, headers=headers, follow_redirects=True, timeout=60)
                    img_path = str(DOWNLOADS_DIR / f"_live_img_{uuid.uuid4().hex[:4]}.webp")
                    with open(img_path, "wb") as f:
                        f.write(img_r.content)

                    vid_r = httpx.get(vid_url, headers=headers, follow_redirects=True, timeout=120)
                    vid_path = str(DOWNLOADS_DIR / f"_live_vid_{uuid.uuid4().hex[:4]}.mp4")
                    with open(vid_path, "wb") as f:
                        f.write(vid_r.content)

                    img_out, vid_out = _convert_to_live_photo(img_path, vid_path)

                    try:
                        os.remove(img_path)
                        os.remove(vid_path)
                        os.remove(img_out)
                    except OSError:
                        pass

                    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50] or uuid.uuid4().hex[:12]
                    _schedule_cleanup(vid_out)
                    return vid_out, f"{safe_title}_live_photo.mov"
                else:
                    raise ValueError("缺少图片或视频")
            else:
                if len(video_urls) == 1:
                    filepath, filename = _download_douyin_video(info, quality)
                elif len(video_urls) > 1:
                    idx = min(live_photo_index, len(video_urls) - 1)
                    single_info = dict(info)
                    single_info["video_url"] = video_urls[idx]
                    single_info["video_urls"] = [video_urls[idx]]
                    filepath, filename = _download_douyin_video(single_info, quality)
                else:
                    raise ValueError("未找到动图视频")
        else:
            filepath, filename = _download_douyin_video(info, quality)
    elif _is_twitter(url):
        filepath, filename = _download_twitter_video(url)
    elif _is_kuaishou(url):
        filepath, filename = _download_kuaishou_video(url)
    elif _is_bilibili(url):
        filepath, filename = _download_bilibili_video(url)
    elif _is_tiktok(url):
        filepath, filename = _download_tiktok(url)
    else:
        raise ValueError("不支持的平台链接")

    if media_type == "mp3" and not filename.endswith(".mp3") and not filename.endswith(".zip"):
        mp3_path = _convert_to_mp3(filepath)
        mp3_name = str(Path(filename).with_suffix(".mp3"))
        _schedule_cleanup(mp3_path)
        return mp3_path, mp3_name

    return filepath, filename


def _download_douyin_video(info: dict, quality: str = "1080p") -> tuple[str, str]:
    """Download Douyin video via streaming HTTP with optimized chunk size."""
    video_url = info["video_url"]
    if not video_url:
        raise ValueError("未能提取视频下载地址")

    video_url = apply_quality(video_url, quality)

    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50]
    filename = f"{safe_title}.mp4" if safe_title else f"{uuid.uuid4().hex[:12]}.mp4"
    filepath = str(DOWNLOADS_DIR / filename)

    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.iesdouyin.com/"}

    with httpx.stream(
        "GET",
        video_url,
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
    ) as r:
        content_length = int(r.headers.get("content-length", 0))

        if content_length == 0 and "aweme.snssdk.com" in video_url:
            vid_match = re.search(r"video_id=([^&]+)", video_url)
            if vid_match:
                direct_url = vid_match.group(1)
                with httpx.stream(
                    "GET",
                    direct_url,
                    headers={"User-Agent": MOBILE_UA},
                    follow_redirects=True,
                    timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
                ) as r2:
                    content_length = int(r2.headers.get("content-length", 0))
                    chunk_size = get_optimal_chunk_size(content_length)
                    with open(filepath, "wb") as f:
                        for chunk in r2.iter_bytes(chunk_size):
                            f.write(chunk)
                _schedule_cleanup(filepath)
                return filepath, filename

        # 根据文件大小动态选择分块大小
        chunk_size = get_optimal_chunk_size(content_length)

        with open(filepath, "wb") as f:
            for chunk in r.iter_bytes(chunk_size):
                f.write(chunk)

    _schedule_cleanup(filepath)
    return filepath, filename


def _download_live_photos(info: dict) -> tuple[str, str]:
    """Download and merge multiple live photos into one video."""
    video_urls = info.get("video_urls", [])
    if not video_urls:
        raise ValueError("未找到动图视频")

    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50] or uuid.uuid4().hex[:12]
    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"}

    def download_single_video(i_url):
        i, url = i_url
        try:
            r = httpx.get(url, headers=headers, follow_redirects=True, timeout=120)
            if len(r.content) < 1000 or r.content[:1] == b"<":
                return None
            vid_path = str(DOWNLOADS_DIR / f"_live_{i}_{uuid.uuid4().hex[:4]}.mp4")
            with open(vid_path, "wb") as f:
                f.write(r.content)
            return vid_path
        except Exception as e:
            logger.warning(f"下载动图视频失败 [{i}]: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(video_urls), 4)) as executor:
        vid_paths = list(filter(None, executor.map(download_single_video, enumerate(video_urls))))

    if len(vid_paths) == 1:
        out_path = str(DOWNLOADS_DIR / f"{safe_title}.mp4")
        os.rename(vid_paths[0], out_path)
        _schedule_cleanup(out_path)
        return out_path, f"{safe_title}.mp4"

    concat_file = str(DOWNLOADS_DIR / f"_concat_live_{uuid.uuid4().hex[:4]}.txt")
    with open(concat_file, "w") as f:
        for v in vid_paths:
            f.write(f"file '{os.path.abspath(v)}'\n")

    out_path = str(DOWNLOADS_DIR / f"{safe_title}.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_file,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True)

    for v in vid_paths:
        try:
            os.remove(v)
        except OSError:
            pass
    try:
        os.remove(concat_file)
    except OSError:
        pass

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {result.stderr[:500]}")

    _schedule_cleanup(out_path)
    return out_path, f"{safe_title}.mp4"


def _convert_to_live_photo(image_path: str, video_path: str) -> tuple[str, str]:
    """Convert image and video to Apple Live Photo format."""
    content_id = str(uuid.uuid4()).upper()

    output_name = f"live_{uuid.uuid4().hex[:8]}"
    output_image = str(DOWNLOADS_DIR / f"{output_name}.jpg")
    output_video = str(DOWNLOADS_DIR / f"{output_name}.mov")

    try:
        from PIL import Image

        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(output_image, "JPEG", quality=95)
    except ImportError:
        import shutil

        shutil.copy2(image_path, output_image)
    except Exception as e:
        logger.warning(f"图片转换失败: {e}")
        import shutil

        shutil.copy2(image_path, output_image)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "24",
        "-movflags",
        "+faststart+use_metadata_tags",
        "-metadata:s:v",
        f"ContentIdentifier={content_id}",
        output_video,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error(f"视频转换失败: {result.stderr.decode()[:500]}")
        raise RuntimeError("视频转换失败")

    try:
        cmd_exiftool = ["exiftool", "-overwrite_original", f"-ContentIdentifier={content_id}", output_image]
        result = subprocess.run(cmd_exiftool, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError("exiftool failed")
    except (FileNotFoundError, RuntimeError):
        temp_img = str(DOWNLOADS_DIR / f"_temp_{uuid.uuid4().hex[:4]}.jpg")
        cmd_img = [
            "ffmpeg",
            "-y",
            "-i",
            output_image,
            "-movflags",
            "+use_metadata_tags",
            "-metadata:s:v",
            f"ContentIdentifier={content_id}",
            temp_img,
        ]
        result = subprocess.run(cmd_img, capture_output=True)
        if result.returncode == 0 and os.path.exists(temp_img):
            os.replace(temp_img, output_image)
        else:
            if os.path.exists(temp_img):
                os.remove(temp_img)
            logger.warning("无法给图片添加 ContentIdentifier")

    logger.info(f"Live Photo 转换成功: {content_id}")

    _schedule_cleanup(output_image)
    _schedule_cleanup(output_video)

    return output_image, output_video


def _download_twitter_video(url: str) -> tuple[str, str]:
    """Download Twitter/X video via fxtwitter API."""
    info = extract_video_info(url)
    m3u8_url = info.get("m3u8_url", "")
    video_url = info.get("video_url", "")
    if not video_url and not m3u8_url:
        raise ValueError("未能提取视频下载地址")

    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50]
    filename = f"{safe_title}.mp4" if safe_title else f"{uuid.uuid4().hex[:12]}.mp4"
    filepath = str(DOWNLOADS_DIR / filename)

    downloaded = False
    if video_url:
        try:
            headers = {"User-Agent": MOBILE_UA, "Referer": "https://x.com/"}
            _curl_download(video_url, filepath, timeout=30, headers=headers, use_proxy=True)
            if os.path.getsize(filepath) > 1000:
                downloaded = True
        except Exception:
            pass

    if not downloaded and m3u8_url and ".m3u8" in m3u8_url:
        if "/pl/" in m3u8_url and "/pl/avc1/" not in m3u8_url:
            m3u8_text = _curl_get(m3u8_url, timeout=15)
            stream_match = None
            for line in m3u8_text.splitlines():
                if "/pl/avc1/" in line:
                    stream_match = line
            if stream_match:
                if stream_match.startswith("/"):
                    m3u8_url = "https://video.twimg.com" + stream_match
                else:
                    base_url = m3u8_url.rsplit("/", 1)[0]
                    m3u8_url = base_url + "/" + stream_match

        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        cmd = ["ffmpeg", "-y"]
        if proxy:
            cmd += ["-http_proxy", proxy]
        cmd += ["-i", m3u8_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", filepath]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise ValueError("ffmpeg failed: " + result.stderr.decode("utf-8", errors="replace")[-200:])
        downloaded = True

    if not downloaded:
        raise ValueError("无法下载视频")

    _schedule_cleanup(filepath)
    return filepath, filename


def _download_single_photo(info: dict, index: int = 0) -> tuple[str, str]:
    """Download a single image from a Douyin photo note."""
    images = info.get("images", [])
    if not images:
        raise ValueError("未能提取图片地址")

    idx = max(0, min(index, len(images) - 1))
    img_url = images[idx]

    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.iesdouyin.com/"}
    r = httpx.get(img_url, headers=headers, follow_redirects=True, timeout=60)

    ct = r.headers.get("content-type", "")
    if "jpeg" in ct or "jpg" in ct:
        ext = ".jpg"
    elif "png" in ct:
        ext = ".png"
    elif "gif" in ct:
        ext = ".gif"
    elif "webp" in ct:
        ext = ".webp"
    else:
        if ".gif" in img_url:
            ext = ".gif"
        elif ".png" in img_url:
            ext = ".png"
        elif ".jpg" in img_url or ".jpeg" in img_url:
            ext = ".jpg"
        else:
            ext = ".webp"

    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50]
    filename = f"{safe_title}_{idx + 1}{ext}" if safe_title else f"{uuid.uuid4().hex[:12]}{ext}"
    filepath = str(DOWNLOADS_DIR / filename)

    with open(filepath, "wb") as f:
        f.write(r.content)

    _schedule_cleanup(filepath)
    return filepath, filename


def _download_all_photos(info: dict) -> list[tuple[str, str]]:
    """并行下载所有图片，返回所有文件路径"""
    images = info.get("images", [])
    if not images:
        raise ValueError("未能提取图片地址")

    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50] or uuid.uuid4().hex[:12]
    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.iesdouyin.com/"}

    def download_single(i_url):
        i, url = i_url
        try:
            r = httpx.get(url, headers=headers, follow_redirects=True, timeout=60)
            ct = r.headers.get("content-type", "")
            if "jpeg" in ct or "jpg" in ct:
                ext = ".jpg"
            elif "png" in ct:
                ext = ".png"
            elif "gif" in ct:
                ext = ".gif"
            else:
                ext = ".webp"
            filename = f"{safe_title}_{i + 1}{ext}"
            filepath = str(DOWNLOADS_DIR / filename)
            with open(filepath, "wb") as f:
                f.write(r.content)
            _schedule_cleanup(filepath)
            return (filepath, filename)
        except Exception as e:
            logger.warning(f"下载图片失败 [{i}]: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(images), 4)) as executor:
        results = list(filter(None, executor.map(download_single, enumerate(images))))

    if not results:
        raise ValueError("无法下载图片")

    return results


def _download_tiktok(url: str) -> tuple[str, str]:
    """Download TikTok video via streaming HTTP."""
    info = extract_video_info(url)
    video_url = info.get("hd_url") or info.get("video_url", "")
    if not video_url:
        raise ValueError("未能提取视频下载地址")

    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50]
    filename = f"{safe_title}.mp4" if safe_title else f"{uuid.uuid4().hex[:12]}.mp4"
    filepath = str(DOWNLOADS_DIR / filename)

    with httpx.stream(
        "GET",
        video_url,
        headers={"User-Agent": MOBILE_UA},
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
    ) as r:
        content_length = int(r.headers.get("content-length", 0))
        chunk_size = get_optimal_chunk_size(content_length)
        with open(filepath, "wb") as f:
            for chunk in r.iter_bytes(chunk_size):
                f.write(chunk)

    _schedule_cleanup(filepath)
    return filepath, filename


def _download_kuaishou_video(url: str) -> tuple[str, str]:
    """Download Kuaishou video via streaming HTTP."""
    info = extract_video_info(url)
    video_url = info.get("hd_url") or info.get("video_url", "")
    if not video_url:
        raise ValueError("未能提取视频下载地址")

    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50]
    filename = f"{safe_title}.mp4" if safe_title else f"{uuid.uuid4().hex[:12]}.mp4"
    filepath = str(DOWNLOADS_DIR / filename)

    with httpx.stream(
        "GET",
        video_url,
        headers={"User-Agent": MOBILE_UA},
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
        verify=False,
    ) as r:
        content_length = int(r.headers.get("content-length", 0))
        chunk_size = get_optimal_chunk_size(content_length)
        with open(filepath, "wb") as f:
            for chunk in r.iter_bytes(chunk_size):
                f.write(chunk)

    _schedule_cleanup(filepath)
    return filepath, filename


def _download_bilibili_video(url: str) -> tuple[str, str]:
    """Download Bilibili video via streaming HTTP."""
    info = extract_video_info(url)
    video_url = info.get("video_url", "")
    if not video_url:
        raise ValueError("未能提取视频下载地址")

    headers = {"User-Agent": MOBILE_UA, "Referer": "https://www.bilibili.com/"}
    safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", info["title"])[:50]
    filename = f"{safe_title}.mp4" if safe_title else f"{uuid.uuid4().hex[:12]}.mp4"
    filepath = str(DOWNLOADS_DIR / filename)

    with httpx.stream(
        "GET",
        video_url,
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
    ) as r:
        content_length = int(r.headers.get("content-length", 0))
        chunk_size = get_optimal_chunk_size(content_length)
        with open(filepath, "wb") as f:
            for chunk in r.iter_bytes(chunk_size):
                f.write(chunk)

    _schedule_cleanup(filepath)
    return filepath, filename


def download_video_for_stream(video_url: str, m3u8_url: str = "") -> tuple[str, str]:
    """Download a video from its CDN URL for streaming."""
    _ensure_downloads_dir()

    safe_name = f"{uuid.uuid4().hex[:12]}.mp4"
    filepath = str(DOWNLOADS_DIR / safe_name)

    downloaded = False
    if video_url and "video.twimg.com" in video_url:
        try:
            headers = {"User-Agent": MOBILE_UA, "Referer": "https://x.com/"}
            _curl_download(video_url, filepath, timeout=30, headers=headers)
            if os.path.getsize(filepath) > 1000:
                downloaded = True
        except Exception:
            pass

    if not downloaded and m3u8_url and ".m3u8" in m3u8_url:
        if "/pl/" in m3u8_url and "/pl/avc1/" not in m3u8_url:
            m3u8_text = _curl_get(m3u8_url, timeout=15)
            stream_match = None
            for line in m3u8_text.splitlines():
                if "/pl/avc1/" in line:
                    stream_match = line
            if stream_match:
                if stream_match.startswith("/"):
                    m3u8_url = "https://video.twimg.com" + stream_match
                else:
                    base_url = m3u8_url.rsplit("/", 1)[0]
                    m3u8_url = base_url + "/" + stream_match

        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
        cmd = ["ffmpeg", "-y"]
        if proxy:
            cmd += ["-http_proxy", proxy]
        cmd += ["-i", m3u8_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", filepath]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise ValueError("ffmpeg failed: " + result.stderr.decode("utf-8", errors="replace")[-200:])
        downloaded = True

    if not downloaded:
        headers = {"User-Agent": MOBILE_UA}
        if "douyin" in video_url or "snssdk" in video_url:
            headers["Referer"] = "https://www.iesdouyin.com/"
        elif "video.twimg.com" in video_url:
            headers["Referer"] = "https://x.com/"
        elif "tiktokcdn" in video_url:
            headers["Referer"] = "https://www.tiktok.com/"
        elif "bilibili" in video_url or "bilivideo" in video_url or "hdslb" in video_url:
            headers["Referer"] = "https://www.bilibili.com/"

        needs_curl = "tiktokcdn" in video_url or "tiktok" in video_url or "ssstiktok" in video_url
        if needs_curl:
            _curl_download(video_url, filepath, timeout=120, headers=headers)
        else:
            verify = "kwaicdn" not in video_url and "kuaishou" not in video_url
            with httpx.stream(
                "GET",
                video_url,
                headers=headers,
                follow_redirects=True,
                timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
                verify=verify,
            ) as r:
                content_length = int(r.headers.get("content-length", 0))
                chunk_size = get_optimal_chunk_size(content_length)
                with open(filepath, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size):
                        f.write(chunk)

    _schedule_cleanup(filepath)
    return filepath, safe_name


# 清理调度器
_cleanup_queue: list[tuple[float, str]] = []
_cleanup_lock = threading.Lock()
_cleanup_started = False


def _schedule_cleanup(filepath: str):
    """Schedule file deletion after 10 minutes."""
    global _cleanup_started
    with _cleanup_lock:
        _cleanup_queue.append((time.time() + 600, filepath))
        if not _cleanup_started:
            _cleanup_started = True
            t = threading.Thread(target=_cleanup_worker, daemon=True)
            t.start()


def _cleanup_worker():
    """Background thread that checks and deletes expired files every 30 seconds."""
    scan_counter = 0
    while True:
        time.sleep(30)
        now = time.time()
        with _cleanup_lock:
            expired = [f for t, f in _cleanup_queue if t <= now]
            _cleanup_queue[:] = [(t, f) for t, f in _cleanup_queue if t > now]
        for fp in expired:
            try:
                if os.path.exists(fp):
                    os.remove(fp)
            except OSError:
                pass
        scan_counter += 1
        if scan_counter >= 10:
            scan_counter = 0
            try:
                _ensure_downloads_dir()
                cutoff = now - 600
                for f in DOWNLOADS_DIR.iterdir():
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        try:
                            f.unlink()
                        except OSError:
                            pass
            except Exception:
                pass


def cleanup_old_files(max_age_seconds: int = 1800):
    """Delete download files older than max_age_seconds."""
    _ensure_downloads_dir()
    now = time.time()
    deleted = 0
    for f in DOWNLOADS_DIR.iterdir():
        if f.is_file():
            try:
                if now - f.stat().st_mtime > max_age_seconds:
                    f.unlink()
                    deleted += 1
            except OSError:
                pass
    if deleted:
        print(f"[cleanup] Removed {deleted} old file(s) from downloads/")
