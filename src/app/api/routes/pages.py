"""HTML pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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


ADMIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Admin</title>
<style>body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:24px;background:#f8f9fb;color:#111}table{width:100%;border-collapse:collapse;background:#fff}td,th{padding:10px;border-bottom:1px solid #e6e8ec;text-align:left;vertical-align:top}input,button{padding:10px;border-radius:8px;border:1px solid #d8dbe2}button{background:#111;color:#fff;border:0}.login{max-width:360px}.muted{color:#667085}</style></head>
<body><section id="login" class="login"><h1>Admin</h1><input id="u" placeholder="用户名"><input id="p" placeholder="密码" type="password"><button id="b">登录</button><p id="e" class="muted"></p></section><section id="panel" hidden><h1>解析记录</h1><table><thead><tr><th>时间</th><th>平台</th><th>类型</th><th>标题</th><th>IP</th><th>URL</th></tr></thead><tbody id="rows"></tbody></table></section>
<script>
const text = (value) => document.createTextNode(String(value ?? ""));
function cell(row, value) { const td = document.createElement("td"); td.appendChild(text(value)); row.appendChild(td); }
async function loadRows() {
  const resp = await fetch("/api/admin/records");
  if (!resp.ok) return;
  document.getElementById("login").hidden = true;
  document.getElementById("panel").hidden = false;
  const rows = document.getElementById("rows");
  rows.textContent = "";
  for (const item of await resp.json()) {
    const tr = document.createElement("tr");
    cell(tr, item.ts ? new Date(item.ts * 1000).toLocaleString() : "");
    cell(tr, item.platform); cell(tr, item.type); cell(tr, item.title); cell(tr, item.ip); cell(tr, item.url);
    rows.appendChild(tr);
  }
}
document.getElementById("b").addEventListener("click", async () => {
  const resp = await fetch("/api/admin/login", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({username:document.getElementById("u").value, password:document.getElementById("p").value})});
  if (resp.ok) loadRows(); else document.getElementById("e").textContent = "登录失败或后台未启用";
});
loadRows();
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
def admin_login_page(settings: AppSettings = Depends(settings_dep)) -> HTMLResponse | RedirectResponse:
    if settings.security.admin_external_url:
        return RedirectResponse(settings.security.admin_external_url, status_code=302)
    return HTMLResponse(ADMIN_HTML)


@router.get("/admin", response_model=None)
def admin_page(settings: AppSettings = Depends(settings_dep)) -> HTMLResponse | RedirectResponse:
    if settings.security.admin_external_url:
        return RedirectResponse(settings.security.admin_external_url, status_code=302)
    return HTMLResponse(ADMIN_HTML)
