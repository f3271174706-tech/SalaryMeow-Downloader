# 更新日志

## [1.0.1] - 2026-07-09

### 性能优化
- 集成 f2 API 模式，解析速度提升 3-4 倍
- 智能分块下载：根据文件大小动态调整（32KB-256KB）
- 新增 Range 支持检测工具（range_checker.py）
- 禁用自动剪切板检测，改为手动粘贴

### Bug 修复
- 修复解析过程中下载按钮可点击导致的 400 错误
- 修复 /api/stream 中 video_id 误用为 URL 的问题
- 修复 f2 库未安装导致 API 模式失败

### 项目结构
- 按照 Python 最佳实践模板重构项目结构
- 源码迁移到 `src/douyin_downloader/` 包结构
- 添加 `pyproject.toml` 现代项目配置
- 添加 Ruff 替代 flake8 + isort + black
- 添加 `.pre-commit-config.yaml`
- 添加 `Makefile` 快捷命令
- 添加测试框架和基础测试

## [1.0.0] - 初始版本

- 多平台无水印下载支持（抖音、TikTok、B站、Twitter、快手）
- Liquid Glass UI 3.0 + Classic Dark + WebGL 三套 UI
- 流式代理 + Range 支持
- Admin 管理后台
- 安全防护（SSRF、CSP、CORS）

### 项目重构
- 按照 Python 最佳实践模板重构项目结构
- 源码迁移到 `src/douyin_downloader/` 包结构
- 添加 `pyproject.toml` 现代项目配置
- 添加 Ruff 替代 flake8 + isort + black
- 添加 `.pre-commit-config.yaml`
- 添加 `Makefile` 快捷命令
- 添加测试框架和基础测试
- 添加初始化脚本（setup.ps1 / setup.sh）
- 更新所有导入路径为包导入

### 文件结构
```
src/douyin_downloader/
├── __init__.py
├── main.py          # FastAPI 路由
├── config.py        # 配置管理
├── downloader.py    # 下载引擎
├── douyin_api.py    # API 模块
└── utils.py         # 工具函数
```

## [2.x] - 历史版本

- 多平台无水印下载支持
- Liquid Glass UI 3.0
- 流式代理 + Range 支持
- Admin 管理后台
- 安全防护（SSRF、CSP、CORS）
