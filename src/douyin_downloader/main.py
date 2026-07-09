import hashlib
import hmac
import ipaddress
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import Response

from douyin_downloader.downloader import (
    DOWNLOADS_DIR,
    MOBILE_UA,
    apply_quality,
    cleanup_old_files,
    download_video,
    download_video_for_stream,
    extract_video_info,
)

# SSRF 防护：允许的域名白名单
ALLOWED_DOMAINS = {
    # 抖音
    "douyin.com",
    "douyinpic.com",
    "douyinvod.com",
    "douyincdn.com",
    "iesdouyin.com",
    "snssdk.com",
    "bytecdn.cn",
    "bytedance.com",
    "zjcdn.com",
    "bdstatic.com",
    "pstatp.com",
    # Twitter/X
    "twitter.com",
    "x.com",
    "t.co",
    "twimg.com",
    "twttr.com",
    "pscp.tv",
    "tweetdeck.com",
    # TikTok
    "tiktok.com",
    "tiktokv.com",
    "ttwstatic.com",
    "tiktokcdn.com",
    # B站
    "bilibili.com",
    "bilivideo.com",
    "hdslb.com",
    "bilivideo.cn",
    # 快手
    "kuaishou.com",
    "gifshow.com",
    "kwaicdn.com",
    "kwaicdn2.com",
    "oskwai.com",
    # 通用 CDN
    "sf11-cdn-tos.douyinstatic.com",
    "sf6-cdn-tos.douyinstatic.com",
    # TikTok 下载
    "ssstiktok.cc",
    "snaptik.app",
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
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return False
        except ValueError:
            pass
        return any(hostname == d or hostname.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


app = FastAPI(
    title="抖音/X 无水印下载器",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.on_event("startup")
async def startup_cleanup():
    cleanup_old_files(max_age_seconds=600)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://fzpnowm.top",
        "https://www.fzpnowm.top",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.add_middleware(GZipMiddleware, minimum_size=500)

# 安全响应头中间件
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdnjs.cloudflare.com static.cloudflareinsights.com; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com; "
            "font-src 'self' fonts.gstatic.com; "
            "img-src 'self' data: https: blob:; "
            "media-src 'self' https: blob:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none';"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

# ---- Admin 认证配置 ----
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
ADMIN_SECRET = secrets.token_hex(32)
ADMIN_SESSION_TTL = 86400
ADMIN_MAX_ATTEMPTS = 5
ADMIN_LOCKOUT_SECONDS = 900
_admin_login_attempts = {}

# ---- 直连认证配置 ----
DIRECT_INVITE_CODE = os.environ.get("DIRECT_INVITE_CODE", "")
DIRECT_AUTH_ENABLED = bool(DIRECT_INVITE_CODE)

# ---- 邀请码暴力破解防护 ----
from collections import defaultdict

_invite_attempts = defaultdict(list)
_invite_MAX_ATTEMPTS = 5
_invite_LOCKOUT_SECONDS = 300


# 邀请码登录页面
DIRECT_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>邀请码验证</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: #f5f5f7;
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
}
.login-card {
  width: 360px; padding: 40px;
  background: rgba(255,255,255,0.6);
  backdrop-filter: blur(80px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.7);
  border-radius: 24px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.06);
}
h1 { font-size: 22px; font-weight: 600; color: rgba(0,0,0,0.85); margin-bottom: 8px; }
.sub { font-size: 13px; color: rgba(0,0,0,0.4); margin-bottom: 28px; }
.field { margin-bottom: 16px; }
.field input {
  width: 100%; padding: 12px 16px;
  background: rgba(255,255,255,0.5);
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 12px;
  font-size: 15px; color: rgba(0,0,0,0.85);
  outline: none;
}
.field input:focus { border-color: rgba(100,150,255,0.5); }
.btn {
  width: 100%; padding: 12px;
  background: rgba(0,0,0,0.8); color: #fff;
  border: none; border-radius: 12px;
  font-size: 15px; font-weight: 500; cursor: pointer;
}
.btn:hover { opacity: 0.85; }
.error {
  background: rgba(255,59,48,0.08);
  border: 1px solid rgba(255,59,48,0.2);
  color: rgba(255,59,48,0.9);
  font-size: 13px; padding: 10px 14px;
  border-radius: 10px; margin-bottom: 16px;
  display: none;
}
</style>
</head>
<body>
<div class="login-card">
  <h1>🔐 邀请码验证</h1>
  <p class="sub">请输入邀请码以访问</p>
  <div class="error" id="error"></div>
  <form id="loginForm">
    <div class="field">
      <input type="text" id="code" name="code" placeholder="请输入邀请码" required autofocus>
    </div>
    <button type="submit" class="btn">验证</button>
  </form>
</div>
<script>
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const code = document.getElementById('code').value;
  try {
    const resp = await fetch('/api/verify-invite', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code})
    });
    if (resp.ok) {
      window.location.reload();
    } else {
      const data = await resp.json();
      document.getElementById('error').textContent = data.detail || '邀请码错误';
      document.getElementById('error').style.display = 'block';
    }
  } catch(e) {
    document.getElementById('error').textContent = '网络错误';
    document.getElementById('error').style.display = 'block';
  }
});
</script>
</body>
</html>"""


def _make_invite_token(code: str) -> str:
    """生成邀请码验证token"""
    payload = f"{code}:{int(time.time()) // 86400}"
    sig = hashlib.sha256(f"{payload}:{DIRECT_INVITE_CODE}".encode()).hexdigest()
    return f"{payload}:{sig}"


def _verify_invite_token(token: str) -> bool:
    """验证邀请码token"""
    if not token or not DIRECT_INVITE_CODE:
        return False
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        code, day_round, sig = parts
        payload = f"{code}:{day_round}"
        expected = hashlib.sha256(f"{payload}:{DIRECT_INVITE_CODE}".encode()).hexdigest()
        return hmac.compare_digest(sig, expected) and code == DIRECT_INVITE_CODE
    except Exception:
        return False


class DirectAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not DIRECT_AUTH_ENABLED:
            return await call_next(request)

        is_cloudflare = "cf-connecting-ip" in request.headers
        if is_cloudflare:
            return await call_next(request)

        invite_token = request.cookies.get("direct_invite", "")
        if _verify_invite_token(invite_token):
            return await call_next(request)

        if request.url.path == "/api/verify-invite":
            return await call_next(request)

        if request.url.path.startswith("/static/"):
            return await call_next(request)

        if request.url.path.startswith("/api/"):
            return await call_next(request)

        response = HTMLResponse(DIRECT_LOGIN_HTML, status_code=200)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(DirectAuthMiddleware)

static_dir = Path(__file__).resolve().parent.parent.parent / "static"
static_dir.mkdir(exist_ok=True)

# 预下载缓存
import concurrent.futures
import threading

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
_preload_cache = {}
_preload_lock = threading.Lock()
_PRELOAD_TTL = 600
_PRELOAD_MAX = 50


def _make_session_token(username: str) -> str:
    """生成 HMAC 签名的 session token"""
    payload = f"{username}:{int(time.time()) // ADMIN_SESSION_TTL}"
    sig = hmac.new(ADMIN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_session_token(token: str) -> bool:
    """验证 session token 有效性"""
    if not token or not ADMIN_PASS:
        return False
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        username, day_round, sig = parts
        payload = f"{username}:{day_round}"
        expected = hmac.new(ADMIN_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected) and username == ADMIN_USER
    except Exception:
        return False


class CachedStaticFiles(StaticFiles):
    """Static files with Cache-Control headers and gzip support."""

    async def get_response(self, path: str, scope):
        accept_encoding = scope.get("headers", [])
        supports_gzip = False
        for header_name, header_value in accept_encoding:
            if header_name == b"accept-encoding" and b"gzip" in header_value:
                supports_gzip = True
                break

        if supports_gzip and path.endswith((".js", ".css")):
            gz_path = f"{path}.gz"
            gz_file = static_dir / gz_path
            if gz_file.exists():
                response = await super().get_response(gz_path, scope)
                if response.status_code == 200:
                    response.headers["Content-Encoding"] = "gzip"
                    response.headers["Vary"] = "Accept-Encoding"
                    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
                    return response

        response = await super().get_response(path, scope)
        if response.status_code == 200 and isinstance(response, Response):
            if path.endswith((".js", ".css", ".jpg", ".png", ".webp", ".gif", ".ico")):
                response.headers["Cache-Control"] = "public, max-age=604800, immutable"
            elif path.endswith(".html"):
                response.headers["Cache-Control"] = "public, max-age=600"
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
    live_photo_index: int = 0


# 启动时缓存 HTML 到内存
_html_cache: dict[str, str] = {}


def _load_html_cache():
    for name in ["index.html", "index-v1.html", "index-v2.html"]:
        path = static_dir / name
        if path.exists():
            _html_cache[name] = path.read_text(encoding="utf-8")


_load_html_cache()


@app.get("/")
async def index():
    html = _html_cache.get("index.html")
    if html:
        return HTMLResponse(html, headers={"Cache-Control": "public, max-age=600"})
    return HTMLResponse("<h1>index.html not found</h1>", status_code=404)


@app.get("/v1")
async def index_v1():
    html = _html_cache.get("index-v1.html")
    if html:
        return HTMLResponse(html, headers={"Cache-Control": "public, max-age=600"})
    return HTMLResponse("<h1>index-v1.html not found</h1>", status_code=404)


@app.get("/v2")
async def index_v2():
    html = _html_cache.get("index-v2.html")
    if html:
        return HTMLResponse(html, headers={"Cache-Control": "public, max-age=600"})
    return HTMLResponse("<h1>index-v2.html not found</h1>", status_code=404)


class InviteRequest(BaseModel):
    code: str


@app.post("/api/verify-invite")
async def verify_invite(req: InviteRequest, request: Request):
    """验证邀请码"""
    if not DIRECT_AUTH_ENABLED:
        return {"ok": True, "message": "直连认证未启用"}

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    _invite_attempts[client_ip] = [t for t in _invite_attempts[client_ip] if now - t < _invite_LOCKOUT_SECONDS]

    if len(_invite_attempts[client_ip]) >= _invite_MAX_ATTEMPTS:
        remaining = int(_invite_LOCKOUT_SECONDS - (now - _invite_attempts[client_ip][0]))
        raise HTTPException(status_code=429, detail=f"尝试次数过多，请 {remaining} 秒后再试")

    _invite_attempts[client_ip].append(now)

    if req.code == DIRECT_INVITE_CODE:
        _invite_attempts[client_ip] = []
        token = _make_invite_token(req.code)
        response = HTMLResponse('{"ok":true}')
        response.set_cookie(
            key="direct_invite",
            value=token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=604800,
        )
        return response
    else:
        raise HTTPException(status_code=401, detail="邀请码错误")


LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

# IP 地理定位缓存
_ip_location_cache: dict[str, str] = {}


def _get_ip_location(ip: str) -> str:
    """查询 IP 物理地址"""
    if not ip or ip in ("127.0.0.1", "::1", "unknown"):
        return ""
    if ip in _ip_location_cache:
        return _ip_location_cache[ip]
    try:
        r = httpx.get(f"https://api.ip.sb/geoip/{ip}", timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            loc = " ".join(filter(None, [data.get("country"), data.get("region"), data.get("city")]))
            if loc:
                _ip_location_cache[ip] = loc
                return loc
    except Exception:
        pass
    try:
        r = httpx.get(f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city", timeout=3)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                loc = " ".join(filter(None, [data.get("country"), data.get("regionName"), data.get("city")]))
                _ip_location_cache[ip] = loc
                return loc
    except Exception:
        pass
    _ip_location_cache[ip] = ""
    return ""


def log_parse_record(url: str, platform: str, media_type: str, title: str, ip: str = ""):
    """记录解析记录到日志文件"""
    import datetime
    import json

    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "parse_records.jsonl"
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
    location = _get_ip_location(ip)

    record = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "ip": ip,
        "location": location,
        "url": url,
        "platform": platform,
        "type": media_type,
        "title": title[:100],
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[监控] 记录失败: {e}")


@app.get("/admin/login")
def admin_login_page():
    """Admin 登录页面"""
    if not ADMIN_PASS:
        return HTMLResponse("<h1>未设置 ADMIN_PASS 环境变量，Admin 功能不可用</h1>", status_code=503)
    # 简化版登录页面
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin 登录</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', -apple-system, sans-serif; background: #f5f5f7; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.login-card { width: 360px; padding: 40px; background: rgba(255,255,255,0.6); backdrop-filter: blur(80px); border: 1px solid rgba(255,255,255,0.7); border-radius: 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.06); }
h1 { font-size: 22px; font-weight: 600; color: rgba(0,0,0,0.85); margin-bottom: 8px; }
.sub { font-size: 13px; color: rgba(0,0,0,0.4); margin-bottom: 28px; }
.field { margin-bottom: 16px; }
.field label { display: block; font-size: 12px; font-weight: 500; color: rgba(0,0,0,0.5); margin-bottom: 6px; }
.field input { width: 100%; padding: 12px 16px; background: rgba(255,255,255,0.5); border: 1px solid rgba(0,0,0,0.08); border-radius: 12px; font-size: 15px; outline: none; }
.field input:focus { border-color: rgba(100,150,255,0.5); }
.btn { width: 100%; padding: 12px; background: rgba(0,0,0,0.8); color: #fff; border: none; border-radius: 12px; font-size: 15px; cursor: pointer; margin-top: 8px; }
.btn:hover { opacity: 0.85; }
.error { background: rgba(255,59,48,0.08); border: 1px solid rgba(255,59,48,0.2); color: rgba(255,59,48,0.9); font-size: 13px; padding: 10px 14px; border-radius: 10px; margin-bottom: 16px; display: none; }
</style>
</head>
<body>
<div class="login-card">
  <h1>🔐 Admin</h1>
  <p class="sub">输入密码以访问管理后台</p>
  <div class="error" id="error"></div>
  <form id="loginForm">
    <div class="field"><label>用户名</label><input type="text" id="username" required></div>
    <div class="field"><label>密码</label><input type="password" id="password" required></div>
    <button type="submit" class="btn">登录</button>
  </form>
</div>
<script>
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errEl = document.getElementById('error');
  errEl.style.display = 'none';
  try {
    const resp = await fetch('/api/admin/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: document.getElementById('username').value, password: document.getElementById('password').value})
    });
    if (resp.ok) { window.location.href = '/admin'; }
    else { const data = await resp.json(); errEl.textContent = data.detail || '登录失败'; errEl.style.display = 'block'; }
  } catch(e) { errEl.textContent = '网络错误'; errEl.style.display = 'block'; }
});
</script>
</body>
</html>"""
    return HTMLResponse(html)


@app.post("/api/admin/login")
async def admin_login(request: Request):
    """Admin 登录接口"""
    if not ADMIN_PASS:
        raise HTTPException(status_code=503, detail="未设置 ADMIN_PASS 环境变量")

    client_ip = request.client.host if request.client else "unknown"

    if client_ip in _admin_login_attempts:
        attempt = _admin_login_attempts[client_ip]
        elapsed = time.time() - attempt["last_attempt"]
        if elapsed > ADMIN_LOCKOUT_SECONDS * 2:
            del _admin_login_attempts[client_ip]
        elif attempt["count"] >= ADMIN_MAX_ATTEMPTS:
            if elapsed < ADMIN_LOCKOUT_SECONDS:
                remaining = int(ADMIN_LOCKOUT_SECONDS - elapsed)
                raise HTTPException(status_code=429, detail=f"登录失败次数过多，请 {remaining} 秒后再试")
            else:
                _admin_login_attempts[client_ip] = {"count": 0, "last_attempt": time.time()}

    if len(_admin_login_attempts) > 100:
        now = time.time()
        expired = [ip for ip, a in _admin_login_attempts.items() if now - a["last_attempt"] > ADMIN_LOCKOUT_SECONDS * 2]
        for ip in expired[:10]:
            del _admin_login_attempts[ip]

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求格式错误")

    username = body.get("username", "")
    password = body.get("password", "")

    if not hmac.compare_digest(username, ADMIN_USER) or not hmac.compare_digest(password, ADMIN_PASS):
        if client_ip not in _admin_login_attempts:
            _admin_login_attempts[client_ip] = {"count": 0, "last_attempt": time.time()}
        _admin_login_attempts[client_ip]["count"] += 1
        _admin_login_attempts[client_ip]["last_attempt"] = time.time()
        remaining = ADMIN_MAX_ATTEMPTS - _admin_login_attempts[client_ip]["count"]
        logger.warning(f"[Admin] 登录失败: IP={client_ip}, 用户名={username}")
        if remaining > 0:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        else:
            raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")

    _admin_login_attempts.pop(client_ip, None)
    logger.info(f"[Admin] 登录成功: IP={client_ip}")

    token = _make_session_token(username)
    response = HTMLResponse('{"ok":true}')
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=ADMIN_SESSION_TTL,
    )
    return response


@app.post("/api/admin/logout")
def admin_logout():
    """Admin 登出"""
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("admin_session")
    return response


@app.get("/admin")
def admin_page(request: Request):
    """管理后台页面"""
    if not ADMIN_PASS:
        return HTMLResponse("<h1>未设置 ADMIN_PASS 环境变量，Admin 功能不可用</h1>", status_code=503)
    token = request.cookies.get("admin_session", "")
    if not _verify_session_token(token):
        return RedirectResponse(url="/admin/login", status_code=302)
    # 返回简化版管理页面
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>后台管理</title>
<script src="/static/tailwindcss.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', -apple-system, sans-serif; background: #f5f5f7; min-height: 100vh; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
.glass { background: rgba(255,255,255,0.6); backdrop-filter: blur(80px) saturate(180%); border: 1px solid rgba(255,255,255,0.7); border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.06); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 20px; }
.stat-card { background: rgba(255,255,255,0.5); backdrop-filter: blur(60px); border: 1px solid rgba(255,255,255,0.7); border-radius: 16px; padding: 14px; text-align: center; }
.stat-card .label { font-size: 11px; color: rgba(0,0,0,0.28); text-transform: uppercase; }
.stat-card .value { font-size: 28px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; }
th { background: rgba(255,255,255,0.4); padding: 12px 16px; text-align: left; font-size: 12px; color: rgba(0,0,0,0.5); text-transform: uppercase; }
td { padding: 12px 16px; border-top: 1px solid rgba(0,0,0,0.04); font-size: 14px; }
tr:hover { background: rgba(0,0,0,0.02); }
.platform { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: 500; }
.platform.douyin { background: rgba(254,44,85,0.1); color: #fe2c55; }
.platform.tiktok { background: rgba(0,0,0,0.08); }
.platform.twitter { background: rgba(29,161,242,0.1); color: #1da1f2; }
.platform.bilibili { background: rgba(0,161,214,0.1); color: #00a1d6; }
.platform.kuaishou { background: rgba(255,73,6,0.1); color: #ff4906; }
</style>
</head>
<body>
<div class="container">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
    <h1 style="font-size:24px;font-weight:600;">解析记录</h1>
    <form method="POST" action="/api/admin/logout"><button type="submit" style="font-size:13px;color:rgba(0,0,0,0.4);padding:8px 16px;border-radius:10px;background:rgba(255,255,255,0.4);border:1px solid rgba(0,0,0,0.06);cursor:pointer;">登出</button></form>
  </div>
  <div class="stats" id="stats"></div>
  <div class="glass" style="overflow:hidden;">
    <table>
      <thead><tr><th>时间</th><th>IP</th><th>平台</th><th>类型</th><th>标题</th></tr></thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>
</div>
<script>
let allRecords = [];
async function loadRecords() {
  try { const resp = await fetch('/api/admin/records'); allRecords = await resp.json(); updateStats(); renderTable(); } catch(e) { console.error('加载失败:', e); }
}
function updateStats() {
  const stats = {}; allRecords.forEach(r => { stats[r.platform] = (stats[r.platform] || 0) + 1; });
  document.getElementById('stats').innerHTML = `
    <div class="stat-card"><div class="label">总解析</div><div class="value">${allRecords.length}</div></div>
    <div class="stat-card"><div class="label">抖音</div><div class="value">${stats.douyin || 0}</div></div>
    <div class="stat-card"><div class="label">Twitter</div><div class="value">${stats.twitter || 0}</div></div>
    <div class="stat-card"><div class="label">B站</div><div class="value">${stats.bilibili || 0}</div></div>
  `;
}
function renderTable() {
  const tbody = document.getElementById('tableBody');
  if (!allRecords.length) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:40px;color:rgba(0,0,0,0.28);">暂无记录</td></tr>'; return; }
  tbody.innerHTML = allRecords.map(r => {
    let time = r.timestamp || '';
    const parts = time.match(/(\\d{2}):(\\d{2}):(\\d{2})/);
    if (parts) time = `${parts[1]}:${parts[2]}`;
    return `<tr><td style="color:rgba(0,0,0,0.28);font-size:13px;">${time}</td><td style="font-size:12px;font-family:monospace;">${r.ip || '-'}</td><td><span class="platform ${r.platform}">${r.platform}</span></td><td>${r.type}</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${r.title || '-'}</td></tr>`;
  }).join('');
}
loadRecords(); setInterval(loadRecords, 30000);
</script>
</body>
</html>"""
    return HTMLResponse(html)


# 记录解析缓存
_records_cache = {"records": [], "mtime": 0, "size": 0}


@app.get("/api/admin/records")
def get_parse_records(request: Request, platform: str = "", type: str = ""):
    """获取解析记录"""
    if ADMIN_PASS:
        token = request.cookies.get("admin_session", "")
        if not _verify_session_token(token):
            raise HTTPException(status_code=401, detail="未登录")
    log_file = LOGS_DIR / "parse_records.jsonl"
    if not log_file.exists():
        return []

    try:
        stat = log_file.stat()
        if stat.st_mtime != _records_cache["mtime"] or stat.st_size != _records_cache["size"]:
            records = []
            with open(log_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        import json

                        records.append(json.loads(line))
                    except Exception:
                        continue
            _records_cache["records"] = records
            _records_cache["mtime"] = stat.st_mtime
            _records_cache["size"] = stat.st_size
    except Exception:
        return []

    records = list(_records_cache["records"])

    if platform:
        records = [r for r in records if r.get("platform") == platform]
    if type:
        records = [r for r in records if r.get("type") == type]

    records.reverse()
    return records


def _preload_video(url: str):
    """后台预下载视频"""
    try:
        with _preload_lock:
            if url in _preload_cache:
                entry = _preload_cache[url]
                if time.time() - entry["timestamp"] < _PRELOAD_TTL and os.path.exists(entry["path"]):
                    return
                else:
                    del _preload_cache[url]
        logger.info(f"开始预下载: {url[:50]}")
        info = extract_video_info(url)
        if info.get("type") != "video" or not info.get("video_url"):
            return
        video_url = info["video_url"]
        title = info.get("title", "video")
        safe_title = re.sub(r'[\n\r\t\\/*?:"<>|#]', "", title)[:50] or uuid.uuid4().hex[:12]
        filename = f"{safe_title}.mp4"
        filepath = str(DOWNLOADS_DIR / filename)

        headers = {"User-Agent": MOBILE_UA}
        referer_map = {
            "douyin": "https://www.iesdouyin.com/",
            "snssdk": "https://www.iesdouyin.com/",
            "video.twimg.com": "https://x.com/",
            "tiktokcdn": "https://www.tiktok.com/",
            "bilibili": "https://www.bilibili.com/",
            "bilivideo": "https://www.bilibili.com/",
            "kwaicdn": "https://www.kuaishou.com/",
            "kuaishou": "https://www.kuaishou.com/",
            "oskwai": "https://www.kuaishou.com/",
        }
        for domain, ref in referer_map.items():
            if domain in video_url:
                headers["Referer"] = ref
                break

        is_foreign = any(d in video_url for d in ["video.twimg.com", "tiktokcdn", "tiktokv.com", "ttwstatic.com"])
        proxy = "http://127.0.0.1:7890" if is_foreign else None

        with httpx.stream(
            "GET",
            video_url,
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
            proxy=proxy,
        ) as r:
            if r.status_code >= 400:
                logger.warning(f"预下载失败: HTTP {r.status_code} for {video_url[:80]}")
                return
            with open(filepath, "wb") as f:
                for chunk in r.iter_bytes(65536):
                    f.write(chunk)
        with _preload_lock:
            if len(_preload_cache) >= _PRELOAD_MAX:
                oldest = min(_preload_cache, key=lambda k: _preload_cache[k]["timestamp"])
                del _preload_cache[oldest]
            _preload_cache[url] = {"path": filepath, "filename": filename, "timestamp": time.time()}
        logger.info(f"预下载完成: {filename}")
    except Exception as e:
        logger.warning(f"预下载失败: {e}")


@app.post("/api/parse")
def parse_video(req: ParseRequest, request: Request):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="请输入视频链接")

    try:
        info = extract_video_info(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {e!s}")

    media_type = info.get("type", "video")
    platform = info.get("platform", "unknown")
    title = info.get("title", "")

    cf_ip = request.headers.get("CF-Connecting-IP", "")
    xff = request.headers.get("X-Forwarded-For", "")
    xff_ipv4 = ""
    for part in xff.split(","):
        part = part.strip()
        if part and ":" not in part and not part.startswith("3."):
            xff_ipv4 = part
            break
    client_ip = xff_ipv4 or cf_ip or (request.client.host if request.client else "")
    log_parse_record(url, platform, media_type, title, ip=client_ip)

    if media_type == "video" and info.get("video_url"):
        try:
            _thread_pool.submit(_preload_video, url)
        except Exception:
            pass

    result = {
        "success": True,
        "title": title,
        "thumbnail": info.get("thumbnail", ""),
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
    """流式代理 + Range 支持"""
    video_url = unquote(video_url)
    m3u8_url = unquote(m3u8_url) if m3u8_url else ""

    if not _validate_url(video_url):
        raise HTTPException(status_code=400, detail="不允许的视频 URL")
    if m3u8_url and not _validate_url(m3u8_url):
        raise HTTPException(status_code=400, detail="不允许的 M3U8 URL")

    if "douyin" in video_url or "snssdk" in video_url:
        video_url = apply_quality(video_url, quality)

    if m3u8_url and ".m3u8" in m3u8_url:
        file_path, filename = download_video_for_stream(video_url, m3u8_url)
        return FileResponse(path=file_path, media_type="video/mp4", filename=filename)

    headers = {"User-Agent": MOBILE_UA}
    referer_map = {
        "douyin": "https://www.iesdouyin.com/",
        "snssdk": "https://www.iesdouyin.com/",
        "video.twimg.com": "https://x.com/",
        "tiktokcdn": "https://www.tiktok.com/",
        "bilibili": "https://www.bilibili.com/",
        "bilivideo": "https://www.bilibili.com/",
        "kwaicdn": "https://www.kuaishou.com/",
        "kuaishou": "https://www.kuaishou.com/",
    }
    for domain, ref in referer_map.items():
        if domain in video_url:
            headers["Referer"] = ref
            break

    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    try:
        is_foreign = any(d in video_url for d in ["video.twimg.com", "tiktokcdn", "tiktokv.com", "ttwstatic.com"])
        client_kwargs = {"follow_redirects": True, "timeout": httpx.Timeout(connect=10, read=300, write=10, pool=10)}
        if is_foreign:
            client_kwargs["proxy"] = "http://127.0.0.1:7890"
        else:
            client_kwargs["trust_env"] = False
        client = httpx.AsyncClient(**client_kwargs)
        req = client.build_request("GET", video_url, headers=headers)
        stream_resp = await client.send(req, stream=True)

        final_url = str(stream_resp.url)
        if final_url != video_url and not _validate_url(final_url):
            await stream_resp.aclose()
            await client.aclose()
            raise HTTPException(status_code=400, detail="不允许重定向到该地址")

        content_length = int(stream_resp.headers.get("content-length", 0))
        if content_length == 0 and "aweme.snssdk.com" in video_url:
            await stream_resp.aclose()
            # 尝试用不同的 ratio 重试
            retry_url = re.sub(r"ratio=\w+", "ratio=720p", video_url)
            if retry_url != video_url:
                req = client.build_request("GET", retry_url, headers=headers)
                stream_resp = await client.send(req, stream=True)
                content_length = int(stream_resp.headers.get("content-length", 0))

        if stream_resp.status_code >= 400:
            await stream_resp.aclose()
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"源返回 {stream_resp.status_code}")

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
        raise HTTPException(status_code=502, detail=f"流式连接失败: {e!s}")


@app.post("/api/download")
def download_video_api(req: DownloadRequest):
    from urllib.parse import quote

    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="请输入视频链接")

    cache_hit = False
    if req.type == "video" and not req.live_photo_format:
        with _preload_lock:
            if url in _preload_cache:
                entry = _preload_cache[url]
                if time.time() - entry["timestamp"] < _PRELOAD_TTL and os.path.exists(entry["path"]):
                    file_path, filename = entry["path"], entry["filename"]
                    del _preload_cache[url]
                    cache_hit = True
                    logger.info(f"预下载缓存命中: {filename}")
                else:
                    del _preload_cache[url]
                    logger.info("预下载缓存过期或文件不存在，重新下载")

    if not cache_hit:
        if not (req.type == "video" and not req.live_photo_format):
            logger.info(f"预下载缓存未命中 (type={req.type})")
        try:
            file_path, filename = download_video(
                url,
                quality=req.quality,
                media_type=req.type,
                image_index=req.image_index,
                live_photo_format=req.live_photo_format,
                live_photo_index=req.live_photo_index,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"下载失败: {e!s}")

    if filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".zip"):
        media_type = "application/zip"
    elif filename.endswith(".webp") or filename.endswith(".jpg") or filename.endswith(".png"):
        media_type = "image/" + filename.rsplit(".", 1)[-1]
    else:
        media_type = "video/mp4"

    encoded_name = quote(filename)
    file_size = os.path.getsize(file_path)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_name}",
            "X-File-Size": str(file_size),
            "Access-Control-Expose-Headers": "X-File-Size, Content-Disposition",
        },
    )
