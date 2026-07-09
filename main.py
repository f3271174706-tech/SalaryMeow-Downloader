from pathlib import Path
from urllib.parse import unquote, urlparse
import ipaddress
import re

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from pydantic import BaseModel

from downloader import MOBILE_UA, apply_quality, cleanup_old_files, download_video_for_stream, extract_video_info, download_video

# SSRF 防护：允许的域名白名单
ALLOWED_DOMAINS = {
    # 抖音
    "douyin.com", "douyinpic.com", "douyinvod.com", "douyincdn.com",
    "iesdouyin.com", "snssdk.com", "bytecdn.cn", "bytedance.com",
    "zjcdn.com", "bdstatic.com", "pstatp.com",
    # Twitter/X
    "twitter.com", "x.com", "t.co", "twimg.com", "twttr.com",
    "pscp.tv", "tweetdeck.com",
    # TikTok
    "tiktok.com", "tiktokv.com", "ttwstatic.com", "tiktokcdn.com",
    # B站
    "bilibili.com", "bilivideo.com", "hdslb.com", "bilivideo.cn",
    # 快手
    "kuaishou.com", "gifshow.com",
    # 通用 CDN
    "sf11-cdn-tos.douyinstatic.com", "sf6-cdn-tos.douyinstatic.com",
    # TikTok 下载
    "ssstiktok.cc", "snaptik.app",
}


def _validate_url(url: str) -> bool:
    """校验 URL 是否在白名单中，防止 SSRF 攻击"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # 检查是否是 IP 地址（拒绝内网地址）
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return False
        except ValueError:
            pass  # 不是 IP，是域名，继续检查
        # 检查域名白名单
        return any(hostname == d or hostname.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False

app = FastAPI(title="抖音/X 无水印下载器")

@app.on_event("startup")
async def startup_cleanup():
    cleanup_old_files()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# gzip 压缩（>500B 的响应自动压缩）
app.add_middleware(GZipMiddleware, minimum_size=500)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)


class CachedStaticFiles(StaticFiles):
    """Static files with Cache-Control headers for better performance."""
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200 and isinstance(response, Response):
            # JS/CSS/图片：缓存 7 天
            if path.endswith(('.js', '.css', '.jpg', '.png', '.webp', '.gif', '.ico')):
                response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
            # HTML：缓存 10 分钟（方便更新）
            elif path.endswith('.html'):
                response.headers['Cache-Control'] = 'public, max-age=600'
        return response


app.mount("/static", CachedStaticFiles(directory=str(static_dir)), name="static")


class ParseRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    quality: str = "1080p"
    type: str = "video"
    image_index: int = 0
    live_photo_format: bool = False


@app.get("/")
async def index():
    from fastapi.responses import HTMLResponse
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"), headers={"Cache-Control": "public, max-age=600"})
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)


@app.get("/v1")
async def index_v1():
    from fastapi.responses import HTMLResponse
    html_path = static_dir / "index-v1.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"), headers={"Cache-Control": "public, max-age=600"})
    return HTMLResponse("<h1>index-v1.html not found</h1>", status_code=404)


@app.get("/v2")
async def index_v2():
    from fastapi.responses import HTMLResponse
    html_path = static_dir / "index-v2.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"), headers={"Cache-Control": "public, max-age=600"})
    return HTMLResponse("<h1>index-v2.html not found</h1>", status_code=404)


LOGS_DIR = Path("/root/DOWN/logs")

def log_parse_record(url: str, platform: str, media_type: str, title: str):
    """记录解析记录到日志文件"""
    import datetime
    import json
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "parse_records.jsonl"

    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "url": url,
        "platform": platform,
        "type": media_type,
        "title": title[:100]
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[监控] 记录失败: {e}")


@app.get("/admin")
def admin_page():
    """管理后台页面 - Liquid Glass 风格"""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>后台管理 - 解析记录</title>
<link rel="icon" type="image/x-icon" href="/static/favicon.ico">
<script src="/static/tailwindcss.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;14..32,400;14..32,500;14..32,600&display=swap');

:root {
  --glass-bg: rgba(255,255,255,0.55);
  --glass-border: rgba(0,0,0,0.06);
  --text-primary: rgba(0,0,0,0.85);
  --text-secondary: rgba(0,0,0,0.5);
  --text-tertiary: rgba(0,0,0,0.28);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: #f5f5f7;
  color: var(--text-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

/* Ambient background */
.bg-ambient {
  position: fixed; inset: 0; z-index: 0;
  background:
    radial-gradient(ellipse 70% 50% at 25% 20%, rgba(120,180,255,0.2), transparent 60%),
    radial-gradient(ellipse 50% 40% at 80% 30%, rgba(200,160,255,0.18), transparent 55%),
    radial-gradient(ellipse 60% 45% at 35% 75%, rgba(255,180,200,0.15), transparent 60%),
    radial-gradient(ellipse 40% 30% at 70% 80%, rgba(160,220,255,0.12), transparent 50%),
    #f5f5f7;
}

/* Liquid Glass */
.glass {
  background: rgba(255,255,255,0.6);
  backdrop-filter: blur(80px) saturate(180%);
  -webkit-backdrop-filter: blur(80px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.7);
  box-shadow:
    0 0 0 0.5px rgba(255,255,255,0.5) inset,
    0 8px 32px rgba(0,0,0,0.06);
}

.glass-card {
  background: rgba(255,255,255,0.5);
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.7);
  position: relative;
  box-shadow:
    0 0 0 0.5px rgba(255,255,255,0.6) inset,
    0 1px 0 rgba(255,255,255,0.4) inset,
    0 16px 48px rgba(0,0,0,0.08),
    0 4px 12px rgba(0,0,0,0.04);
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
  position: relative;
  z-index: 1;
}

h1 {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 24px;
}

/* Stats grid */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: rgba(255,255,255,0.5);
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.7);
  border-radius: 16px;
  padding: 14px;
  text-align: center;
  box-shadow:
    0 0 0 0.5px rgba(255,255,255,0.5) inset,
    0 4px 16px rgba(0,0,0,0.04);
  transition: transform 0.2s;
}

.stat-card:hover {
  transform: translateY(-1px);
}

.stat-card .label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 500;
}

.stat-card .value {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Filters */
.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.filters select, .filters input {
  padding: 10px 14px;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 12px;
  font-size: 14px;
  background: rgba(255,255,255,0.6);
  backdrop-filter: blur(20px);
  color: var(--text-primary);
  outline: none;
  font-family: inherit;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.filters select:focus, .filters input:focus {
  border-color: rgba(0,0,0,0.15);
  box-shadow: 0 0 0 3px rgba(0,0,0,0.04);
}

.filters input::placeholder { color: var(--text-tertiary); }
.filters input { flex: 1; min-width: 200px; }

/* Table */
.table-wrapper {
  background: rgba(255,255,255,0.5);
  backdrop-filter: blur(60px) saturate(180%);
  -webkit-backdrop-filter: blur(60px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.7);
  border-radius: 16px;
  overflow: hidden;
  box-shadow:
    0 0 0 0.5px rgba(255,255,255,0.5) inset,
    0 8px 32px rgba(0,0,0,0.06);
}

table { width: 100%; border-collapse: collapse; }

th {
  background: rgba(255,255,255,0.4);
  padding: 12px 16px;
  text-align: left;
  font-weight: 500;
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}

td {
  padding: 12px 16px;
  border-top: 1px solid rgba(0,0,0,0.04);
  font-size: 14px;
  color: var(--text-primary);
}

tr:hover { background: rgba(0,0,0,0.02); }

.platform {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.platform.douyin { background: rgba(254,44,85,0.1); color: #fe2c55; }
.platform.tiktok { background: rgba(0,0,0,0.08); color: #000; }
.platform.twitter { background: rgba(29,161,242,0.1); color: #1da1f2; }
.platform.bilibili { background: rgba(0,161,214,0.1); color: #00a1d6; }
.platform.kuaishou { background: rgba(255,73,6,0.1); color: #ff4906; }

.type {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.type.video { background: rgba(0,0,0,0.06); color: var(--text-secondary); }
.type.photo { background: rgba(0,0,0,0.06); color: var(--text-secondary); }
.type.live_photo { background: rgba(0,0,0,0.06); color: var(--text-secondary); }

.url-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 280px;
}

.url-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  color: var(--text-secondary);
  font-size: 13px;
  transition: all 0.2s;
}

.url-btn {
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(0,0,0,0.04);
  border: 1px solid rgba(0,0,0,0.06);
  display: inline-block;
}

.url-btn:hover {
  background: rgba(0,0,0,0.08);
  border-color: rgba(0,0,0,0.12);
}

.url-text.expanded {
  white-space: normal;
  word-break: break-all;
  color: var(--text-primary);
  background: rgba(0,0,0,0.02);
}

.url-text.copied {
  color: #22c55e;
}

.title {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time { color: var(--text-tertiary); font-size: 13px; }
.empty { text-align: center; padding: 40px; color: var(--text-tertiary); }

@media (max-width: 768px) {
  .container { padding: 16px; }
  .stats { grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .stat-card .value { font-size: 22px; }
  th, td { padding: 10px 12px; font-size: 13px; }
  .url, .title { max-width: 100px; }
}
</style>
</head>
<body>
<div class="bg-ambient"></div>
<div class="container">
    <h1>解析记录</h1>
    <div class="stats" id="stats"></div>
    <div class="filters">
        <select id="platformFilter">
            <option value="">全部平台</option>
            <option value="douyin">抖音</option>
            <option value="tiktok">TikTok</option>
            <option value="twitter">Twitter</option>
            <option value="bilibili">B站</option>
            <option value="kuaishou">快手</option>
        </select>
        <select id="typeFilter">
            <option value="">全部类型</option>
            <option value="video">视频</option>
            <option value="photo">图片</option>
            <option value="live_photo">动图</option>
        </select>
        <input type="text" id="searchInput" placeholder="搜索标题...">
    </div>
    <div class="table-wrapper">
        <table>
            <thead>
                <tr>
                    <th>时间</th>
                    <th>平台</th>
                    <th>类型</th>
                    <th>标题</th>
                    <th>链接</th>
                </tr>
            </thead>
            <tbody id="tableBody"></tbody>
        </table>
    </div>
</div>
<script>
let allRecords = [];

async function loadRecords() {
    try {
        const resp = await fetch('/api/admin/records');
        allRecords = await resp.json();
        updateStats();
        renderTable();
    } catch(e) {
        console.error('加载失败:', e);
    }
}

function updateStats() {
    const stats = {};
    allRecords.forEach(r => {
        stats[r.platform] = (stats[r.platform] || 0) + 1;
    });
    const total = allRecords.length;
    document.getElementById('stats').innerHTML = `
        <div class="stat-card"><div class="label">总解析</div><div class="value">${total}</div></div>
        <div class="stat-card"><div class="label">抖音</div><div class="value">${stats.douyin || 0}</div></div>
        <div class="stat-card"><div class="label">TikTok</div><div class="value">${stats.tiktok || 0}</div></div>
        <div class="stat-card"><div class="label">Twitter</div><div class="value">${stats.twitter || 0}</div></div>
        <div class="stat-card"><div class="label">B站</div><div class="value">${stats.bilibili || 0}</div></div>
        <div class="stat-card"><div class="label">快手</div><div class="value">${stats.kuaishou || 0}</div></div>
    `;
}

function renderTable() {
    const platform = document.getElementById('platformFilter').value;
    const type = document.getElementById('typeFilter').value;
    const search = document.getElementById('searchInput').value.toLowerCase();

    let filtered = allRecords;
    if (platform) filtered = filtered.filter(r => r.platform === platform);
    if (type) filtered = filtered.filter(r => r.type === type);
    if (search) filtered = filtered.filter(r => (r.title || '').toLowerCase().includes(search));

    const tbody = document.getElementById('tableBody');
    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无记录</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.slice(0, 100).map((r, idx) => {
        const time = new Date(r.timestamp).toLocaleString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit'});
        const typeLabel = {video: '视频', photo: '图片', live_photo: '动图'}[r.type] || r.type;
        const url = r.url || '';
        return `<tr>
            <td class="time">${time}</td>
            <td><span class="platform ${r.platform}">${r.platform}</span></td>
            <td><span class="type ${r.type}">${typeLabel}</span></td>
            <td class="title" title="${r.title}">${r.title || '-'}</td>
            <td class="url-cell">
                <span class="url-text url-btn" id="url-${idx}" onclick="copyUrl(${idx}, '${url.replace(/'/g, "\\'")}')">...</span>
            </td>
        </tr>`;
    }).join('');
}

function copyUrl(idx, url) {
    const el = document.getElementById('url-' + idx);
    if (!url) return;
    // 复制到剪贴板
    navigator.clipboard.writeText(url).then(() => {
        // 展开显示完整链接
        el.textContent = url;
        el.classList.add('expanded');
        el.classList.add('copied');
        // 10秒后恢复
        setTimeout(() => {
            el.textContent = '...';
            el.classList.remove('expanded');
            el.classList.remove('copied');
        }, 10000);
    });
}

document.getElementById('platformFilter').addEventListener('change', renderTable);
document.getElementById('typeFilter').addEventListener('change', renderTable);
document.getElementById('searchInput').addEventListener('input', renderTable);

loadRecords();
setInterval(loadRecords, 30000);
</script>
</body>
</html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html)


@app.get("/api/admin/records")
def get_parse_records(platform: str = "", type: str = "", limit: int = 500):
    """获取解析记录（从 downloader.log 解析）"""
    log_file = LOGS_DIR / "downloader.log"
    if not log_file.exists():
        return []

    records = []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                # 解析 "解析完成" 日志行
                if "解析完成:" in line:
                    try:
                        # 提取时间戳
                        timestamp = line[:19].strip()
                        # 提取 URL
                        url_match = re.search(r'url=(https?://[^\s,]+)', line)
                        url_val = url_match.group(1) if url_match else ""
                        # 提取平台
                        platform_match = re.search(r'platform=(\w+)', line)
                        platform_val = platform_match.group(1) if platform_match else "unknown"
                        # 提取类型
                        type_match = re.search(r'type=(\w+)', line)
                        type_val = type_match.group(1) if type_match else "unknown"
                        # 提取标题
                        title_match = re.search(r'title=(.+?)(?:\s*$)', line)
                        title = title_match.group(1).strip() if title_match else ""

                        records.append({
                            "timestamp": timestamp,
                            "url": url_val,
                            "platform": platform_val,
                            "type": type_val,
                            "title": title
                        })
                    except:
                        continue
    except Exception as e:
        return []

    # 筛选
    if platform:
        records = [r for r in records if r.get("platform") == platform]
    if type:
        records = [r for r in records if r.get("type") == type]

    # 倒序，最新的在前
    records.reverse()
    return records[:limit]


@app.post("/api/parse")
def parse_video(req: ParseRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="请输入视频链接")

    try:
        info = extract_video_info(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")

    media_type = info.get("type", "video")
    platform = info.get("platform", "unknown")
    title = info.get("title", "")

    # 记录解析记录
    log_parse_record(url, platform, media_type, title)

    result = {
        "success": True,
        "title": title,
        "thumbnail": info["thumbnail"],
        "duration": info.get("duration", 0),
        "platform": platform,
        "type": media_type,
    }
    if media_type == "photo":
        result["images"] = info.get("images", [])
        result["video_url"] = ""
        result["music_url"] = info.get("music_url", "")
    elif media_type == "live_photo":
        result["video_url"] = info.get("video_url", "")
        result["video_urls"] = info.get("video_urls", [])
        result["images"] = info.get("images", [])
        result["music_url"] = info.get("music_url", "")
    else:
        result["video_url"] = info.get("video_url", "")
        result["m3u8_url"] = info.get("m3u8_url", "")
    return result


@app.get("/api/stream")
async def stream_video(
    request: Request,
    video_url: str = Query(..., description="Video URL"),
    quality: str = Query("1080p", description="Quality: 720p, 1080p, hd"),
    m3u8_url: str = Query("", description="M3U8 URL for ffmpeg download"),
):
    """流式代理 + Range 支持（边下边传，可拖进度条）"""
    video_url = unquote(video_url)
    m3u8_url = unquote(m3u8_url) if m3u8_url else ""

    # SSRF 防护：校验 URL
    if not _validate_url(video_url):
        raise HTTPException(status_code=400, detail="不允许的视频 URL")
    if m3u8_url and not _validate_url(m3u8_url):
        raise HTTPException(status_code=400, detail="不允许的 M3U8 URL")

    if "douyin" in video_url or "snssdk" in video_url:
        video_url = apply_quality(video_url, quality)

    # m3u8 需要 ffmpeg 处理，走先下载后返回
    if m3u8_url and ".m3u8" in m3u8_url:
        file_path, filename = download_video_for_stream(video_url, m3u8_url)
        return FileResponse(path=file_path, media_type="video/mp4", filename=filename)

    # 构建请求头
    headers = {"User-Agent": MOBILE_UA}
    referer_map = {
        "douyin": "https://www.iesdouyin.com/",
        "snssdk": "https://www.iesdouyin.com/",
        "video.twimg.com": "https://x.com/",
        "tiktokcdn": "https://www.tiktok.com/",
        "bilibili": "https://www.bilibili.com/",
        "bilivideo": "https://www.bilibili.com/",
    }
    for domain, ref in referer_map.items():
        if domain in video_url:
            headers["Referer"] = ref
            break

    # 传递浏览器的 Range 请求头
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    try:
        # 不用 async with，手动管理生命周期，避免 StreamingResponse 迭代前连接被关
        # 国外 CDN 需要代理
        is_foreign = any(d in video_url for d in ["video.twimg.com", "tiktokcdn", "tiktokv.com", "ttwstatic.com"])
        client_kwargs = {"follow_redirects": True, "timeout": httpx.Timeout(connect=10, read=300, write=10, pool=10)}
        if is_foreign:
            client_kwargs["proxy"] = "http://127.0.0.1:7890"
        else:
            client_kwargs["trust_env"] = False
        client = httpx.AsyncClient(**client_kwargs)
        req = client.build_request("GET", video_url, headers=headers)
        stream_resp = await client.send(req, stream=True)

        # Fallback: play URL 返回空内容时，用 CDN 直链
        content_length = int(stream_resp.headers.get("content-length", 0))
        if content_length == 0 and "aweme.snssdk.com" in video_url:
            await stream_resp.aclose()
            vid_match = re.search(r'video_id=([^&]+)', video_url)
            if vid_match:
                direct_url = vid_match.group(1)
                req = client.build_request("GET", direct_url, headers={"User-Agent": MOBILE_UA})
                stream_resp = await client.send(req, stream=True)

        if stream_resp.status_code >= 400:
            await stream_resp.aclose()
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"源返回 {stream_resp.status_code}")

        # 构建响应头
        resp_headers = {}
        for key in ("content-type", "content-length", "content-range", "accept-ranges"):
            val = stream_resp.headers.get(key)
            if val:
                resp_headers[key] = val

        async def chunk_iter():
            try:
                async for chunk in stream_resp.aiter_bytes(65536):
                    yield chunk
            finally:
                await stream_resp.aclose()
                await client.aclose()

        status_code = 206 if (range_header and stream_resp.status_code == 206) else 200
        return StreamingResponse(
            chunk_iter(),
            status_code=status_code,
            headers=resp_headers,
            media_type=stream_resp.headers.get("content-type", "video/mp4"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"流式连接失败: {str(e)}")


@app.post("/api/download")
def download_video_api(req: DownloadRequest):
    import os
    from urllib.parse import quote

    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="请输入视频链接")

    try:
        file_path, filename = download_video(
            url, quality=req.quality, media_type=req.type, image_index=req.image_index,
            live_photo_format=req.live_photo_format
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"下载失败: {str(e)}")

    if filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".zip"):
        media_type = "application/zip"
    elif filename.endswith(".webp") or filename.endswith(".jpg") or filename.endswith(".png"):
        media_type = "image/" + filename.rsplit(".", 1)[-1]
    else:
        media_type = "video/mp4"

    file_size = os.path.getsize(file_path)
    encoded_name = quote(filename)

    def file_iter():
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_iter(),
        media_type=media_type,
        headers={
            "Content-Length": str(file_size),
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_name}",
            "Accept-Ranges": "bytes",
        },
    )
