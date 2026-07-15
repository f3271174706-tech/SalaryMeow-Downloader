"""
工具函数模块
包含重试机制、HTTP 请求封装等通用功能
"""

import subprocess
import time
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

import httpx

from .config import config, get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class RequestError(Exception):
    """请求异常"""

    def __init__(self, message: str, status_code: int = 0, url: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.url = url


def request_with_retry(
    method: str,
    url: str,
    max_retries: Optional[int] = None,
    retry_delay_base: Optional[float] = None,
    **kwargs,
) -> httpx.Response:
    """
    带重试机制的 HTTP 请求

    Args:
        method: 请求方法 (GET, POST, etc.)
        url: 请求 URL
        max_retries: 最大重试次数（默认从配置读取）
        retry_delay_base: 重试间隔基数（默认从配置读取）
        **kwargs: 传递给 httpx 的其他参数

    Returns:
        httpx.Response: 响应对象

    Raises:
        RequestError: 请求失败且重试用尽时抛出
    """
    if max_retries is None:
        max_retries = config.get("network.max_retries", 3)
    if retry_delay_base is None:
        retry_delay_base = config.get("network.retry_delay_base", 1)

    # 设置默认超时
    if "timeout" not in kwargs:
        kwargs["timeout"] = config.get_timeout()

    # 设置默认 follow_redirects
    if "follow_redirects" not in kwargs:
        kwargs["follow_redirects"] = True

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"请求 {method} {url} (尝试 {attempt + 1}/{max_retries + 1})")

            if method.upper() == "GET":
                response = httpx.get(url, **kwargs)
            elif method.upper() == "POST":
                response = httpx.post(url, **kwargs)
            else:
                response = httpx.request(method, url, **kwargs)

            # 检查状态码
            if response.status_code >= 500:
                raise RequestError(
                    f"服务器错误: {response.status_code}",
                    status_code=response.status_code,
                    url=url,
                )

            logger.debug(f"请求成功: {response.status_code}")
            return response

        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            last_error = e
            if attempt < max_retries:
                delay = retry_delay_base * (attempt + 1)
                logger.warning(f"请求失败，{delay}秒后重试: {url} - {type(e).__name__}: {e}")
                time.sleep(delay)
            else:
                logger.error(f"请求失败，已重试 {max_retries} 次: {url} - {e}")

        except RequestError as e:
            last_error = e
            if attempt < max_retries:
                delay = retry_delay_base * (attempt + 1)
                logger.warning(f"服务器错误，{delay}秒后重试: {url} - {e}")
                time.sleep(delay)
            else:
                logger.error(f"服务器错误，已重试 {max_retries} 次: {url} - {e}")

        except Exception as e:
            last_error = e
            logger.error(f"未知错误: {url} - {type(e).__name__}: {e}")
            break  # 未知错误不重试

    raise RequestError(
        f"请求失败: {last_error}",
        url=url,
    )


def get_with_retry(url: str, **kwargs) -> httpx.Response:
    """带重试的 GET 请求"""
    return request_with_retry("GET", url, **kwargs)


def post_with_retry(url: str, **kwargs) -> httpx.Response:
    """带重试的 POST 请求"""
    return request_with_retry("POST", url, **kwargs)


def curl_get(url: str, timeout: int = 30, headers: Optional[Dict] = None) -> str:
    """
    使用 curl 发送 GET 请求（用于绕过代理问题）

    Args:
        url: 请求 URL
        timeout: 超时时间
        headers: 自定义请求头

    Returns:
        str: 响应内容
    """
    user_agent = config.get("user_agent.mobile")
    proxy = config.get_proxy()

    cmd = ["curl", "-s", "-L", "--max-time", str(timeout), "-H", f"User-Agent: {user_agent}"]

    if proxy:
        cmd += ["--proxy", proxy]

    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]

    cmd.append(url)

    logger.debug(f"curl GET: {url}")

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8", errors="replace")[:200]
            logger.error(f"curl 失败: {error_msg}")
            raise RequestError(f"curl failed: {error_msg}", url=url)

        response_text = result.stdout.decode("utf-8", errors="replace")
        logger.debug(f"curl 成功: {len(response_text)} bytes")
        return response_text

    except subprocess.TimeoutExpired:
        logger.error(f"curl 超时: {url}")
        raise RequestError(f"curl 超时", url=url)


def curl_download(
    url: str,
    filepath: str,
    timeout: int = 120,
    headers: Optional[Dict] = None,
) -> int:
    """
    使用 curl 下载文件

    Args:
        url: 下载 URL
        filepath: 保存路径
        timeout: 超时时间
        headers: 自定义请求头

    Returns:
        int: 文件大小
    """
    user_agent = config.get("user_agent.mobile")
    proxy = config.get_proxy()

    try:
        max_bytes = max(1, int(os.environ.get("DOUYIN_MAX_DOWNLOAD_BYTES", str(1024 * 1024 * 1024))))
    except ValueError:
        max_bytes = 1024 * 1024 * 1024
    cmd = [
        "curl", "-sS", "-L", "--proto", "=https", "--max-redirs", "5",
        "--max-filesize", str(max_bytes), "--max-time", str(timeout), "-o", filepath,
    ]

    if proxy:
        cmd += ["--proxy", proxy]

    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    else:
        cmd += ["-H", f"User-Agent: {user_agent}"]

    cmd.append(url)

    logger.debug(f"curl 下载: {url} -> {filepath}")

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        if result.returncode != 0:
            Path(filepath).unlink(missing_ok=True)
            error_msg = result.stderr.decode("utf-8", errors="replace")[:200]
            logger.error(f"curl 下载失败: {error_msg}")
            raise RequestError(f"curl download failed: {error_msg}", url=url)

        import os
        file_size = os.path.getsize(filepath)
        if file_size > max_bytes:
            Path(filepath).unlink(missing_ok=True)
            raise RequestError("下载内容超过大小限制", url=url)
        logger.debug(f"curl 下载完成: {file_size} bytes")
        return file_size

    except subprocess.TimeoutExpired:
        logger.error(f"curl 下载超时: {url}")
        raise RequestError(f"curl 下载超时", url=url)


def detect_platform(url: str) -> Optional[str]:
    """
    检测 URL 所属平台

    Args:
        url: 视频链接

    Returns:
        str: 平台名称，无法识别返回 None
    """
    platform_patterns = {
        "douyin": ["douyin.com", "iesdouyin.com"],
        "twitter": ["twitter.com", "x.com"],
        "tiktok": ["tiktok.com"],
        "bilibili": ["bilibili.com", "b23.tv", "t.bilibili.com"],
        "kuaishou": ["kuaishou.com", "v.kuaishou.com", "gifshow.com"],
    }

    url_lower = url.lower()
    for platform, domains in platform_patterns.items():
        if any(domain in url_lower for domain in domains):
            return platform

    return None


def extract_url(text: str) -> str:
    """
    从用户输入中提取 URL

    Args:
        text: 用户输入（可能包含分享文本）

    Returns:
        str: 提取的 URL
    """
    import re

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
