# 部署

本轮不包含 Docker。

## Windows 本地

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
playwright install chromium
$env:DOUYIN_SESSION_SECRET="dev-session-secret-dev-session-secret"
$env:DOUYIN_INVITE_CODES="dev-code"
python -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 9000
```

ffmpeg 需要在 PATH 中可用。

## Linux 本地

```bash
sudo useradd --system --create-home --home-dir /opt/douyin-downloader-refactor douyin
sudo mkdir -p /opt/douyin-downloader-refactor /var/lib/douyin-downloader /var/log/douyin-downloader
sudo chown -R douyin:douyin /opt/douyin-downloader-refactor /var/lib/douyin-downloader /var/log/douyin-downloader
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
sudo .venv/bin/python -m playwright install-deps chromium
sudo -u douyin env PLAYWRIGHT_BROWSERS_PATH=/opt/douyin-downloader-refactor/.playwright .venv/bin/python -m playwright install chromium
python -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 9000 --workers 1
```

## systemd

1. 复制项目到 `/opt/douyin-downloader-refactor`。
2. 复制 `deploy/systemd/app.env.example` 为 `/etc/douyin-downloader-refactor/app.env` 并填入真实环境变量。
3. 复制 `deploy/systemd/app.service` 到 `/etc/systemd/system/douyin-downloader-refactor.service`。
4. 执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now douyin-downloader-refactor
sudo systemctl status douyin-downloader-refactor
journalctl -u douyin-downloader-refactor -f
```

可选安装定时清理和简单自愈：

```bash
sudo install -m 0644 deploy/systemd/cleanup.service /etc/systemd/system/douyin-downloader-refactor-cleanup.service
sudo install -m 0644 deploy/systemd/cleanup.timer /etc/systemd/system/douyin-downloader-refactor-cleanup.timer
sudo install -m 0644 deploy/systemd/healthcheck.service /etc/systemd/system/douyin-downloader-refactor-healthcheck.service
sudo install -m 0644 deploy/systemd/healthcheck.timer /etc/systemd/system/douyin-downloader-refactor-healthcheck.timer
sudo chmod 0755 /opt/douyin-downloader-refactor/scripts/cleanup_downloads.sh
sudo chmod 0755 /opt/douyin-downloader-refactor/scripts/healthcheck.sh
sudo systemctl daemon-reload
sudo systemctl enable --now douyin-downloader-refactor-cleanup.timer douyin-downloader-refactor-healthcheck.timer
```

清理 timer 默认每 5 分钟删除超过 15 分钟的临时文件；健康检查每 2 分钟访问 `/health/live`，失败时重启应用。若需要同时检查 Tunnel，可在 healthcheck service 中设置 `DOUYIN_TUNNEL_SERVICE_NAME`。

当前建议 `--workers 1`，因为 Session 以外仍有兼容层内存缓存和浏览器池。

浏览器必须使用与 `app.env` 相同的 `PLAYWRIGHT_BROWSERS_PATH` 安装，并确保 `douyin` 用户可读。

## Cloudflare Tunnel

- Tunnel 转发到 `http://127.0.0.1:9000`。
- 应用端口不要直接暴露公网。
- 防火墙限制外部访问应用端口。
- `CF-Connecting-IP` 不是认证依据；仅在可信代理边界启用真实 IP 读取。
- 灰度时先使用测试域名指向新端口，通过后再切正式域名。
- 回滚时把 Tunnel ingress 或反向代理上游切回旧服务端口。
