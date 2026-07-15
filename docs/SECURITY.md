# 安全说明

## 威胁模型

本服务会代表服务器访问用户提交的媒体 URL，因此重点风险是 SSRF、无限流量代理、资源滥用、XSS、秘密泄露和管理接口暴露。

## 已实现

- 解析、下载、流媒体接口需要邀请码会话。
- 管理记录接口需要管理员会话，`ADMIN_PASS` 缺失时默认禁用。
- Session 密钥从配置读取，生产缺失时启动失败。
- URL safety 统一检查协议、hostname、userinfo、端口、平台域名白名单、IP 地址和 DNS 解析后的地址。
- 流媒体重定向逐跳重新校验。
- 兼容层主要下载链路的重定向也逐跳校验，并限制响应大小。
- 下载结果必须位于配置目录内，超限文件会被删除。
- 新后台记录页面使用 DOM API 和 `textContent`，不拼接外部 HTML。
- 默认不信任 `CF-Connecting-IP` / `X-Forwarded-For`。
- CSP 移除 `unsafe-eval`。
- 日志 formatter 对常见 secret 参数做脱敏。

## 已知限制

- 旧兼容层仍有固定第三方 API 请求和 `subprocess.run`，后续应逐个平台迁移到统一 HTTP/ffmpeg 适配器。
- 外部平台 live 测试默认不执行。
- Cookie 轮换仍是进程内状态。
- 限流是单 worker 内存实现，未来多实例需要 Redis 或等价存储。
- Playwright 浏览器池仍在兼容层内，需要灰度观察资源释放。

## 上线前检查

- 轮换旧 `DEPLOY.md` 中出现过的 SSH 私钥和所有真实 Cookie。
- 设置强 `DOUYIN_SESSION_SECRET`、邀请码、管理员密码。
- 应用只监听 `127.0.0.1` 或内网地址。
- 防火墙禁止公网直连应用端口。
- Cloudflare Header 只在可信代理边界启用。
