# Changelog

## Unreleased

- 抖音解析默认仅使用 f2 API；空数据、异常或超时时切换到另一组 Cookie 且只重试一次，
  不再自动回退网页爬虫或 Playwright。
- 抖音短链优先从首次 302 跳转提取作品 ID，避免额外请求两个分享页面。
- 应用启动阶段可预热 f2 抖音请求栈，避免首位用户承担模块初始化延迟。

### 新增

- 新增 `src/app` 分层 FastAPI 应用。
- 新增 URL safety、认证服务、记录服务、限流和健康检查。
- 新增 systemd、Cloudflare Tunnel 示例和 CI。
- 新增安全、契约和配置测试。

### 修改

- 旧解析/下载逻辑迁入 `src/app/legacy` 兼容层。
- API 路由按职责拆分。
- 管理后台默认拒绝，未设置 `ADMIN_PASS` 时禁用。
- Session 密钥改为配置加载。

### 安全修复

- 修复 `/api/admin/records` 在无管理员密码时默认开放的风险。
- 修复高资源 API 可绕过页面认证直接访问的风险。
- 移除兼容层全局 monkey patch `httpx.get/post`。
- 增加 SSRF 域名和 DNS 解析防护。
- 新后台记录页面避免外部数据 `innerHTML` 渲染。
- 默认不信任 Cloudflare 真实 IP 头。
- 流式并发名额现在保持到响应体传输结束。
- 下载文件实施目录边界、磁盘余量、状态码和最大字节数检查。
- 旧下载链路逐跳校验重定向，并恢复快手 TLS 证书验证。
- Session 使用精确签发时间校验，可信代理配置为空时不再信任转发头。
- 修复旧版前端解析结果通过 `innerHTML` 注入图片地址的问题。

### 可靠性修复

- 本地 HTTP 开发默认关闭 Secure Cookie，生产环境强制开启。
- 修复 CI 的 `src` 导入路径。
- 兼容层不再在导入阶段写项目目录日志。
- Playwright 优先使用已安装浏览器，并为 Windows Edge 和 Linux Snap Chromium 提供回退。
- 后台记录增加文件轮转和单次查询数量上限。
- 下载物理文件名增加随机前缀，避免同标题并发覆盖。
- 固定已验证的顶层依赖版本。

### 人工迁移事项

- 轮换旧部署文档中泄露过的 SSH 私钥和真实 Cookie。
- 设置生产 `DOUYIN_SESSION_SECRET`、邀请码和管理员密码。
- 执行灰度 live 平台测试。
