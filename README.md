# Douyin Downloader Refactored

这是从 `D:\mycode\douyin-downloader 3.0` 拆出的生产重构版本。当前版本保留旧项目已验证的解析和下载核心逻辑，并在外层新增 FastAPI `src` 布局、统一配置、URL 安全校验、邀请码/API 认证、管理员默认拒绝、健康检查、测试和部署示例。

## 功能

- 支持抖音、TikTok、X/Twitter、Bilibili、快手的旧解析/下载逻辑兼容层。
- 提供 `/api/parse`、`/api/download`、`/api/stream`、`/api/admin/records` 等兼容 API。
- 新增 `/health/live` 和 `/health/ready`。
- 解析、下载和流媒体接口需要邀请码会话。
- 管理接口需要管理员会话；未设置 `ADMIN_PASS` 时默认禁用。

## 项目结构

```text
src/app/            FastAPI 应用、路由、服务、基础设施
src/app/legacy/     旧项目核心解析/下载兼容层
web/static/         前端静态资源
tests/              单元、契约、安全测试
deploy/             systemd 和 Cloudflare Tunnel 示例
docs/               审计、架构、部署、安全和验证文档
```

## 本地启动

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
$env:DOUYIN_SESSION_SECRET="dev-session-secret-dev-session-secret"
$env:DOUYIN_INVITE_CODES="dev-code"
$env:DOUYIN_SECURE_COOKIES="false"
python -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 9000
```

打开 `http://127.0.0.1:9000`，输入 `dev-code`。

## 检查

```powershell
python -m compileall src
python -c "from app.main import app; print(app.title)"
ruff check .
ruff format --check .
mypy src
pytest
```

## 生产配置

生产环境必须设置：

- `DOUYIN_APP_ENV=production`
- `DOUYIN_SESSION_SECRET`，至少 32 字符
- `DOUYIN_INVITE_CODES`
- `DOUYIN_SECURE_COOKIES=true`
- `ADMIN_PASS`，如果需要后台
- Cookie、代理等真实秘密放在外部环境或不入库的 `config.yaml`

不要提交真实 `DEPLOY.md`、`config.yaml`、Cookie、私钥、Cloudflare Token、日志或下载文件。

## 当前限制

旧平台解析/下载逻辑仍保留在 `src/app/legacy`，本轮没有重写每个平台的所有降级策略。外部平台 live 解析、真实 Cookie、Playwright 浏览器和 ffmpeg 行为需要在灰度环境人工验证。
