"""HTML pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.api.dependencies import get_auth_service, settings_dep
from app.core.settings import AppSettings
from app.services.auth_service import AuthService

router = APIRouter(tags=["pages"])


LOGIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>邀请码验证</title>
<style>body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh;display:grid;place-items:center;background:#f6f7f9;color:#111}.card{width:min(92vw,360px);padding:28px;background:#fff;border:1px solid #e6e8ec;border-radius:12px;box-shadow:0 8px 30px #0001}input,button{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:8px;font-size:15px}input{border:1px solid #d8dbe2}button{margin-top:12px;border:0;background:#111;color:#fff;cursor:pointer}.error{min-height:22px;color:#b42318;font-size:13px;margin-top:10px}</style>
</head>
<body><main class="card"><h1>邀请码验证</h1><form id="f"><input id="code" autocomplete="off" placeholder="请输入邀请码" autofocus><button>验证</button><p class="error" id="err"></p></form></main>
<script>
document.getElementById("f").addEventListener("submit", async (event) => {
  event.preventDefault();
  const err = document.getElementById("err");
  err.textContent = "";
  const resp = await fetch("/api/verify-invite", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({code:document.getElementById("code").value})});
  if (resp.ok) window.location.href = "/";
  else err.textContent = "邀请码错误或已被限流";
});
</script></body></html>"""


@router.get("/")
def index(
    request: Request, settings: AppSettings = Depends(settings_dep), auth: AuthService = Depends(get_auth_service)
):
    try:
        auth.require_invite_session(request)
    except Exception:
        return HTMLResponse(LOGIN_HTML, status_code=401)
    index_path = settings.paths.web_static_dir / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@router.get("/v1")
def index_v1(settings: AppSettings = Depends(settings_dep)):
    return HTMLResponse((settings.paths.web_static_dir / "index-v1.html").read_text(encoding="utf-8"))


@router.get("/v2")
def index_v2(settings: AppSettings = Depends(settings_dep)):
    return HTMLResponse((settings.paths.web_static_dir / "index-v2.html").read_text(encoding="utf-8"))


@router.get("/admin/login", response_model=None)
def admin_login_page(settings: AppSettings = Depends(settings_dep)) -> FileResponse | RedirectResponse:
    if settings.security.admin_external_url:
        return RedirectResponse(settings.security.admin_external_url, status_code=302)
    return FileResponse(settings.paths.web_static_dir.parent / "admin" / "index.html")


@router.get("/admin", response_model=None)
def admin_page(settings: AppSettings = Depends(settings_dep)) -> FileResponse | RedirectResponse:
    if settings.security.admin_external_url:
        return RedirectResponse(settings.security.admin_external_url, status_code=302)
    return FileResponse(settings.paths.web_static_dir.parent / "admin" / "index.html")
