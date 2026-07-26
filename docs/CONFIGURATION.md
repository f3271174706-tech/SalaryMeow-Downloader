# 配置

配置来源优先级：环境变量覆盖 `config.yaml`，没有配置时使用安全默认值。真实秘密不得提交。

关键环境变量：

- `DOUYIN_APP_ENV`：`development` 或 `production`。
- `DOUYIN_SESSION_SECRET`：Session 签名密钥，生产必填，至少 32 字符。
- `DOUYIN_INVITE_CODES`：逗号分隔的邀请码，生产必填。
- `DOUYIN_INVITE_AUTH_ENABLED`：是否启用邀请码保护，默认 `true`；公开站点可设为 `false`。
- `FZP_ADMIN_USER`：管理员用户名，默认 `admin`。
- `FZP_ADMIN_PASSWORD_HASH`：scrypt 管理员密码哈希；缺失时管理模块禁用。
- `FZP_SESSION_SECRET`：Admin 独立会话签名密钥，至少 32 字符。
- `FZP_SESSION_TTL_SECONDS`：Admin 会话有效期，默认 8 小时。
- `FZP_TRUSTED_ORIGINS`：允许登录和退出的同源地址。
- `ADMIN_EXTERNAL_URL`：可选的共享后台地址；设置后 `/admin` 与 `/admin/login` 会跳转过去。
- `DOUYIN_TRUST_PROXY_HEADERS`：是否信任代理头，默认 `false`。
- `DOUYIN_TRUSTED_PROXY_CIDRS`：可信代理 CIDR，启用代理头时建议配置。
- `DOUYIN_METADATA_CACHE_TTL_SECONDS`：元数据缓存秒数，默认 `600`。
- `DOUYIN_METADATA_CACHE_MAX_ENTRIES`：元数据缓存条目上限，默认 `500`。
- `DOUYIN_PRELOAD_ENABLED`：受限智能预下载开关，默认 `false`。
- `DOUYIN_PRELOAD_PLATFORMS`：允许预下载的平台，默认仅 `douyin`。
- `DOUYIN_PRELOAD_MAX_DURATION_SECONDS`：视频时长上限，默认 `180` 秒。
- `DOUYIN_PRELOAD_MAX_BYTES`：单个预下载文件上限，默认 100 MiB。
- `DOUYIN_PRELOAD_CACHE_MAX_BYTES`：预下载缓存总上限，默认 512 MiB。
- `DOUYIN_PRELOAD_CACHE_MAX_ENTRIES`：预下载缓存条目上限，默认 `20`。
- `DOUYIN_PRELOAD_CONCURRENCY`：后台预下载并发，默认 `1`。
- `DOUYIN_PRELOAD_WAIT_SECONDS`：下载请求等待进行中预下载的最长时间，默认 `2` 秒。
- `DOUYIN_DATA_DIR`、`DOUYIN_DOWNLOADS_DIR`、`DOUYIN_LOGS_DIR`：数据、下载和日志目录。
- `DOUYIN_SECURE_COOKIES`：本地 HTTP 开发设为 `false`，生产 HTTPS 必须为 `true`。
- `DOUYIN_MAX_DOWNLOAD_BYTES`、`DOUYIN_MAX_STREAM_BYTES`：单次下载和流式响应的最大字节数。
- `DOUYIN_RECORDS_FILE`：可选的共享解析记录 JSONL 文件路径。
- `DOUYIN_RECORDS_MAX_FILE_BYTES`：记录文件轮转上限；共享旧项目文件时可设为 `0`。

生产差异：

- 生产缺少 `DOUYIN_SESSION_SECRET` 会启动失败；邀请码保护开启时缺少 `DOUYIN_INVITE_CODES` 也会启动失败。
- 生产 Admin 缺少有效的 `FZP_ADMIN_PASSWORD_HASH` 或 `FZP_SESSION_SECRET` 会启动失败。
- 可信代理头默认不启用，Cloudflare Tunnel 部署时只在本机/可信代理边界启用。

Cookie 配置：

真实平台 Cookie 仍由旧兼容层读取，可放入不入库的 `config.yaml` 或后续迁移到环境变量/外部 secrets 文件。配置对象 repr 已脱敏。

智能预下载只处理普通视频，并要求时长已知。缓存文件被用户下载后立即删除；未使用文件由 10 分钟进程内过期机制和服务器定时清理共同回收。
