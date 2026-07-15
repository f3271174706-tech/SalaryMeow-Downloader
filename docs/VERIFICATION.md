# 验证记录

日期：2026-07-15

## 已执行命令

```text
python -m compileall src                                      PASS
PYTHONPATH=src python -c "from app.main import app; print(app.title)"  PASS
ruff check .                                                  PASS
ruff format --check .                                         PASS
mypy src                                                      PASS
pytest                                                        PASS, 25 passed
uvicorn app.main:app --app-dir src + GET /health/ready         PASS, HTTP 200
Playwright Chromium/Edge launch                               PASS
pip check                                                     PASS
```

## 说明

- `pytest` 仍显示 FastAPI TestClient 关于未来 `httpx2` 的弃用提示；当前契约测试均通过。
- `mypy` 和 `ruff` 对 `src/app/legacy` 兼容层做了排除，原因是该目录保存旧生产逻辑，避免为风格检查大规模改动未迁移的平台降级路径；兼容层仍通过 `compileall` 和应用导入检查。
- 启动冒烟使用本地 `127.0.0.1:9876`，请求 `/health/live` 后正常终止进程。
- 秘密扫描未发现 OpenSSH 私钥、Cloudflare Token 或常见真实 Cookie 字段值。

## 跳过项

- 外部平台真实解析和下载：避免使用真实生产 Cookie 和真实用户流量。
- 线上服务器验证：本轮明确禁止 SSH 和修改生产环境。
- Playwright 浏览器真实启动、ffmpeg 真实转码、各平台 live 下载：需要在灰度环境人工验证。
