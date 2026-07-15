# 架构

当前架构采用 `src/app` 分层：

- `api/routes`：FastAPI 路由，只负责请求校验、依赖注入和响应转换。
- `services`：业务编排，包括认证、解析、下载、流媒体和记录。
- `infrastructure`：URL 安全、限流、文件安全等基础设施。
- `core`：设置、日志、安全头、Session 和客户端 IP 信任边界。
- `legacy`：旧生产解析/下载逻辑兼容层。

请求流程：

1. 安全响应头中间件添加 CSP、Frame、MIME 和 Referrer 策略。
2. 高资源 API 通过 `require_invite_session`。
3. 管理 API 通过 `require_admin_session`。
4. URL 进入旧逻辑前由 `url_safety.validate_url` 校验。
5. 服务层调用 `legacy.downloader` 保留原解析和下载能力。
6. 解析记录通过 `RecordService` 写入 `var/logs/parse_records.jsonl`。

解析流程：

```text
/api/parse -> invite session -> rate limit -> concurrency limit -> URL safety -> legacy extractor -> record append -> compatible JSON
```

下载流程：

```text
/api/download -> invite session -> concurrency limit -> URL safety -> legacy download -> FileResponse
```

流媒体流程：

```text
/api/stream -> invite session -> async concurrency limit -> URL safety -> manual redirect validation -> StreamingResponse
```

新增平台建议：

1. 在 `infrastructure/url_safety.py` 添加域名白名单。
2. 在 `services/parser_service.py` 或未来 `platforms/` 适配器中添加平台入口。
3. 增加不访问真实上游的单元测试和契约测试。
4. 再增加可选 live 测试。
