# 配置

配置来源优先级：环境变量覆盖 `config.yaml`，没有配置时使用安全默认值。真实秘密不得提交。

关键环境变量：

- `DOUYIN_APP_ENV`：`development` 或 `production`。
- `DOUYIN_SESSION_SECRET`：Session 签名密钥，生产必填，至少 32 字符。
- `DOUYIN_INVITE_CODES`：逗号分隔的邀请码，生产必填。
- `ADMIN_USER`：管理员用户名，默认 `admin`。
- `ADMIN_PASS`：管理员密码；缺失时管理模块禁用。
- `DOUYIN_TRUST_PROXY_HEADERS`：是否信任代理头，默认 `false`。
- `DOUYIN_TRUSTED_PROXY_CIDRS`：可信代理 CIDR，启用代理头时建议配置。
- `DOUYIN_PRELOAD_ENABLED`：预下载开关，默认 `false`。
- `DOUYIN_DATA_DIR`、`DOUYIN_DOWNLOADS_DIR`、`DOUYIN_LOGS_DIR`：数据、下载和日志目录。
- `DOUYIN_SECURE_COOKIES`：本地 HTTP 开发设为 `false`，生产 HTTPS 必须为 `true`。
- `DOUYIN_MAX_DOWNLOAD_BYTES`、`DOUYIN_MAX_STREAM_BYTES`：单次下载和流式响应的最大字节数。

生产差异：

- 生产缺少 `DOUYIN_SESSION_SECRET` 或 `DOUYIN_INVITE_CODES` 会启动失败。
- 管理后台缺少 `ADMIN_PASS` 不开放记录接口。
- 可信代理头默认不启用，Cloudflare Tunnel 部署时只在本机/可信代理边界启用。

Cookie 配置：

真实平台 Cookie 仍由旧兼容层读取，可放入不入库的 `config.yaml` 或后续迁移到环境变量/外部 secrets 文件。配置对象 repr 已脱敏。
