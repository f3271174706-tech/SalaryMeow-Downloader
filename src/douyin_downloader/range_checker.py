"""Range 请求支持检测工具"""

import httpx
from typing import Optional
from douyin_downloader.config import get_logger

logger = get_logger(__name__)


def check_range_support(url: str, timeout: int = 10) -> dict:
    """
    检测 URL 是否支持 Range 请求

    Args:
        url: 视频 URL
        timeout: 超时时间

    Returns:
        {
            "supported": bool,
            "method": str,  # 检测方法
            "content_length": int,
            "details": dict
        }
    """
    result = {
        "supported": False,
        "method": "unknown",
        "content_length": 0,
        "details": {}
    }

    try:
        # 方法1: HEAD 请求检查
        head_result = _check_by_head(url, timeout)
        if head_result is not None:
            result["supported"] = head_result
            result["method"] = "HEAD"
            return result

        # 方法2: 实际 Range 请求测试
        range_result = _check_by_range(url, timeout)
        result["supported"] = range_result["supported"]
        result["method"] = "RANGE_TEST"
        result["content_length"] = range_result.get("content_length", 0)
        result["details"] = range_result.get("details", {})

    except Exception as e:
        result["details"]["error"] = str(e)
        logger.debug(f"Range 检测失败: {e}")

    return result


def _check_by_head(url: str, timeout: int) -> Optional[bool]:
    """通过 HEAD 响应检查"""
    try:
        resp = httpx.head(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
            follow_redirects=True
        )

        # 检查 Accept-Ranges 头
        accept_ranges = resp.headers.get("Accept-Ranges", "").lower()
        if "bytes" in accept_ranges:
            return True

        # 有些服务器不声明但支持
        return None  # 需要进一步测试

    except:
        return None


def _check_by_range(url: str, timeout: int) -> dict:
    """通过实际 Range 请求测试"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Range": "bytes=0-99",
        }
        resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)

        result = {
            "supported": False,
            "content_length": 0,
            "details": {}
        }

        # 206 = 支持 Range
        if resp.status_code == 206:
            result["supported"] = True
            result["details"]["status"] = 206
            result["details"]["content_range"] = resp.headers.get("Content-Range", "")
            result["details"]["accept_ranges"] = resp.headers.get("Accept-Ranges", "")

            # 解析文件大小
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                try:
                    total_size = int(content_range.split("/")[-1])
                    result["content_length"] = total_size
                except:
                    pass

        # 200 = 不支持，但返回完整文件
        elif resp.status_code == 200:
            result["supported"] = False
            result["details"]["status"] = 200
            result["content_length"] = int(resp.headers.get("content-length", 0))

        else:
            result["details"]["status"] = resp.status_code

        return result

    except Exception as e:
        return {
            "supported": False,
            "content_length": 0,
            "details": {"error": str(e)}
        }


def get_optimal_chunk_size(content_length: int) -> int:
    """
    根据文件大小返回最优的分块大小

    Args:
        content_length: 文件大小（字节）

    Returns:
        最优分块大小（字节）
    """
    if content_length < 1 * 1024 * 1024:      # < 1MB
        return 32768                            # 32KB
    elif content_length < 10 * 1024 * 1024:    # < 10MB
        return 65536                            # 64KB
    elif content_length < 100 * 1024 * 1024:   # < 100MB
        return 131072                           # 128KB
    else:
        return 262144                           # 256KB


def test_range_with_real_video(video_url: str) -> dict:
    """
    用真实视频 URL 测试 Range 支持

    Args:
        video_url: 真实的视频下载 URL

    Returns:
        检测结果
    """
    logger.info(f"测试 Range 支持: {video_url[:60]}...")

    result = check_range_support(video_url)

    if result["supported"]:
        logger.info(f"  ✓ 支持 Range (方法: {result['method']})")
        if result["content_length"]:
            logger.info(f"  ✓ 文件大小: {result['content_length'] / 1024 / 1024:.2f} MB")
    else:
        logger.info(f"  ✗ 不支持 Range")

    return result


# 使用示例
if __name__ == "__main__":
    # 测试示例
    test_url = "https://example.com/video.mp4"
    result = check_range_support(test_url)
    print(f"URL: {test_url}")
    print(f"支持 Range: {result['supported']}")
    print(f"检测方法: {result['method']}")
    print(f"文件大小: {result['content_length']} bytes")
