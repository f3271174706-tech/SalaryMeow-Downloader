# 迁移指南

1. 旧目录结构：`main.py`、`downloader.py`、`config.py`、`static/` 混合在根目录。
2. 新目录结构：`src/app` 分层，旧核心保留在 `src/app/legacy`。
3. 旧启动入口：`main:app`。
4. 新启动入口：`app.main:app --app-dir src`。
5. 旧配置：`config.yaml` 可能包含真实 Cookie。
6. 新配置：环境变量优先，参考 `.env.example` 和 `config.example.yaml`。
7. Session 密钥：生产必须设置 `DOUYIN_SESSION_SECRET`。
8. 管理员配置：设置 `ADMIN_USER` 和 `ADMIN_PASS`；不设置则后台禁用。
9. Cookie 迁移：把真实 Cookie 放到不入库的 `config.yaml` 或外部 secrets。
10. 数据目录：下载文件迁移到 `var/downloads` 或生产 `/var/lib/douyin-downloader/downloads`。
11. 日志迁移：解析记录迁移到 `var/logs/parse_records.jsonl` 或生产日志目录。
12. systemd：使用新 service，独立服务名、独立目录、独立端口。
13. Cloudflare Tunnel：先添加测试域名指向新端口。
14. 灰度验证：首页、邀请码、后台登录、各平台解析、下载、流媒体、Range、Cookie、代理、Playwright、ffmpeg、记录、限流。
15. 正式切换：把正式域名 ingress 切到新端口。
16. 回滚：把正式域名 ingress 切回旧端口，保留旧版本直到观察期结束。
17. 上线前：备份旧目录、配置、日志、解析记录和 Cookie。
18. 上线后：查看健康检查、systemd 状态、日志错误和资源占用。
