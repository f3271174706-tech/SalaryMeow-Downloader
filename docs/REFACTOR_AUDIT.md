# 重构审计报告

审计日期：2026-07-14
源项目：`D:\mycode\douyin-downloader 3.0`
重构目录：`D:\mycode\downloader SaaS-codex`

## 项目概况

旧项目是 Python/FastAPI 单体应用，入口为 `main.py`，主要依赖 FastAPI、Uvicorn、httpx、PyYAML、f2、TikTokApi、Playwright 和 pydantic。旧启动方式推测为在项目根目录直接运行 `uvicorn main:app --host 0.0.0.0 --port 9000` 或 systemd 包装命令。

旧目录包含：

- `main.py`：FastAPI 应用、认证、页面、记录、解析、下载、流媒体混在一起。
- `downloader.py`：平台识别、解析、下载、Playwright、ffmpeg、缓存、清理混在一起。
- `config.py` / `config.yaml`：配置和真实 Cookie。
- `static/index.html`：主前端页面。
- `logs/`、`downloads/`、`preloads/`、`npm-cache/`、`__pycache__/`：运行产物或本地缓存。
- `DEPLOY.md`：包含服务器部署信息，旧版本检查中发现包含敏感 SSH 私钥内容，不能进入交付版本。

## API

旧 API：

- `GET /`、`/v1`、`/v2`：静态页面。
- `POST /api/verify-invite`：邀请码认证。
- `GET /admin/login`、`GET /admin`：后台页面。
- `POST /api/admin/login`、`POST /api/admin/logout`：后台登录/退出。
- `GET /api/admin/records`：解析记录。
- `POST /api/parse`：高资源解析接口，接受外部 URL。
- `GET /api/stream`：高资源流媒体代理，接受外部媒体 URL，支持 Range。
- `POST /api/download`：高资源下载接口，接受外部 URL。

兼容风险：前端依赖这些路径和主要响应字段，本轮保持路径和字段。

## 平台解析

旧项目支持抖音、TikTok、X/Twitter、Bilibili、快手。入口集中在 `downloader.extract_video_info` 和 `downloader.download_video`。平台判断旧实现包含字符串包含判断，存在 `douyin.com.evil.com` 这类混淆风险。本轮新增 `src/app/infrastructure/url_safety.py`，在进入旧兼容层前先做标准 URL 解析、域名白名单、IP 和 DNS 解析结果检查。

Cookie 使用集中在旧 `config.py`，支持按平台读取和轮换。本轮保留兼容层能力，但交付版本不包含真实 `config.yaml`。

Playwright 位于旧 `downloader.py` 的抖音图集和页面提取逻辑。ffmpeg 位于旧下载、音频转换、图集视频合成、m3u8 处理逻辑。

## 状态和存储

旧项目存在多处进程内状态：

- 解析缓存 `_cache`
- 预下载缓存 `_preload_cache`
- 浏览器池 `_browser_pool`
- Cookie 失败标记 `_cookie_failed`
- 管理登录失败次数
- 邀请码失败次数
- 解析记录 `logs/parse_records.jsonl`
- 下载文件 `downloads/`

本轮新增 `RecordService`、限流器和配置集中入口，但旧解析缓存、浏览器池和部分下载缓存仍在兼容层中，文档要求生产暂用单 worker。

## 代码质量

主要问题：

- `main.py` 约 55KB，职责过多。
- `downloader.py` 约 70KB，平台逻辑和基础设施混合。
- 旧 `downloader.py` 全局 monkey patch `httpx.get/post`，会污染进程。
- 旧配置 `Config.__repr__` 可能输出 Cookie。
- 同步/异步混用，包含线程池中执行 `asyncio.run`。
- 多处裸 `except` 和异常吞掉。
- 路由直接处理业务和文件逻辑。

已处理：

- 新增 `src/app` 分层。
- 移除兼容层 `httpx.get/post` monkey patch。
- 配置 repr 脱敏。
- API 路由拆分到 `api/routes`。
- 服务层拆分 parse/download/stream/auth/record。

仍需后续迁移：逐个平台从 `legacy/downloader.py` 迁出，进一步消除同步/异步混用和裸 `except`。

## 安全

实际确认问题：

- 高资源 API 认证边界不够清晰。
- `GET /api/admin/records` 在未配置 `ADMIN_PASS` 时会直接返回记录，存在默认开放风险。
- `ADMIN_SECRET` 每次启动随机，多 worker/session 稳定性差。
- 旧 URL 校验缺少 DNS 解析后 IP 检查，且平台判断存在字符串包含模式。
- 后台旧页面用 `innerHTML` 渲染外部记录字段，存在 XSS 风险。
- 旧逻辑直接信任 `CF-Connecting-IP` 获取用户 IP。
- `DEPLOY.md` 和 `config.yaml` 属于敏感文件，不应进入交付版本。

已处理：

- 解析、下载、流媒体 API 统一需要邀请码会话。
- 管理记录 API 统一需要管理员会话；后台未配置时返回 503。
- Session secret 从环境或 YAML 加载，生产缺失时启动失败。
- 统一 URL safety 模块覆盖 parse/download/stream 入口和 stream 重定向。
- 新后台页面使用 `textContent`/DOM API 渲染记录。
- `CF-Connecting-IP` 仅在显式启用可信代理并匹配可信 CIDR 时读取。
- `.gitignore` 排除真实配置、日志、缓存、私钥和部署秘密。

## 重构风险

- 旧平台解析依赖真实上游页面/API，默认测试不进行真实平台请求。
- f2、TikTokApi、Playwright、ffmpeg 能力需要灰度环境验证。
- 当前仍保留旧兼容层，不能声称所有平台逻辑已完全现代化。
- 内存状态暂不适合多 worker，systemd 示例固定 `--workers 1`。
- Cookie 迁移和轮换必须人工完成。
