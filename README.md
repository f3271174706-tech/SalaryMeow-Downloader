# DOWN — 多平台无水印下载器

<div align="center">

**⚡ 快速解析 | 🎨 三套 UI | 🔌 API 模式 | 📦 流式下载**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ 核心特性

- **🚀 极速解析** — f2 API 模式，解析速度 2-3 秒
- **🎯 多平台支持** — 抖音、TikTok、B站、Twitter/X、快手
- **📺 多种内容** — 视频、图文、实况照片、音乐提取
- **🎨 三套 UI** — Liquid Glass / Classic Dark / WebGL 玻璃
- **⚡ 流式下载** — Range 支持，大文件边下边播
- **🧠 智能分块** — 根据文件大小自动优化下载策略
- **🔄 浏览器池** — 复用实例，避免重复启动

---

## 📊 支持平台

| 平台 | 视频 | 图片 | 动图 | 解析方式 |
|:-----|:----:|:----:|:----:|:---------|
| **抖音** | ✅ | ✅ | ✅ | f2 API（优先）+ HTML 解析 |
| **TikTok** | ✅ | ⚠️ | - | TikTokApi + ssstiktok |
| **B站** | ✅ | - | - | 官方 API |
| **Twitter/X** | ✅ | ✅ | - | fxtwitter API |
| **快手** | ✅ | - | - | HTML 解析 |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+（推荐 3.12/3.13）
- Node.js 18+（可选，用于前端开发）
- ffmpeg（可选，用于视频合成）

### 1. 克隆项目

```bash
git clone https://github.com/f3271174706-tech/SalaryMeow-Downloader.git
cd SalaryMeow-Downloader
```

### 2. 创建虚拟环境

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### 3. 安装依赖

```bash
# 基础安装
pip install -r requirements.txt
pip install -e .

# 完整安装（含 API 库）
pip install -e ".[full]"
```

### 4. 配置

```bash
# 复制配置模板
cp .env.example .env
cp config.yaml.example config.yaml

# 编辑配置
# .env      → 设置 ADMIN_PASS
# config.yaml → 配置 Cookie（可选，提高解析成功率）
```

### 5. 运行

```bash
# 方式 1：使用 Makefile
make run

# 方式 2：直接运行
python -m uvicorn src.douyin_downloader.main:app --host 0.0.0.0 --port 8001 --reload
```

访问 http://localhost:8001

---

## 📁 项目结构

```
douyin-downloader/
├── src/
│   └── douyin_downloader/      # 主代码包
│       ├── __init__.py
│       ├── main.py             # FastAPI 路由 + 流式代理
│       ├── config.py           # 配置管理（单例模式）
│       ├── downloader.py       # 核心下载引擎（分块优化）
│       ├── douyin_api.py       # f2 API 模式
│       ├── range_checker.py    # Range 支持检测
│       └── utils.py            # 工具函数
├── static/                     # 前端文件
│   ├── index.html              # Liquid Glass 3.0 UI
│   ├── index-v1.html           # Classic Dark UI
│   └── index-v2.html           # WebGL Glass UI
├── tests/                      # 测试代码
├── scripts/                    # 初始化脚本
├── docs/                       # 文档
├── config.yaml                 # 配置文件
├── pyproject.toml              # 项目配置
├── requirements.txt            # 依赖列表
├── Makefile                    # 快捷命令
└── .pre-commit-config.yaml     # 代码质量钩子
```

---

## 🎨 UI 版本

| 路由 | 版本 | 风格 | 特点 |
|:-----|:-----|:-----|:-----|
| `/` | Liquid Glass 3.0 | Apple 液态玻璃 | 白色主题，毛玻璃效果 |
| `/v1` | Classic Dark | 经典暗色 | 深色主题，简洁高效 |
| `/v2` | WebGL Glass | 实时渲染 | WebGL 折射效果 |

---

## ⚡ 性能优化

### 解析速度

| 模式 | 耗时 | 说明 |
|:-----|:-----|:-----|
| **f2 API 模式** | ~2 秒 | 直接调用 API，无需解析网页 |
| **爬虫模式** | ~5-7 秒 | 需要多次 HTTP 请求 |

### 下载优化

| 优化项 | 说明 |
|:-------|:-----|
| **智能分块** | <1MB: 32KB / 1-10MB: 64KB / 10-100MB: 128KB / >100MB: 256KB |
| **流式下载** | 内存友好，支持大文件 |
| **Range 支持** | 边下边播，可拖动进度条 |
| **浏览器池** | 复用 Playwright 实例 |

---

## 🔧 配置说明

### config.yaml

```yaml
# Cookie 配置（可选，提高解析成功率）
cookies:
  douyin: "your_douyin_cookie"
  tiktok: "your_tiktok_cookie"
  twitter: "your_twitter_cookie"

# 代理配置
network:
  proxy: "http://127.0.0.1:7890"  # 可选

# API 模式
api:
  enabled: true  # 启用 f2 API 模式

# 日志
logging:
  level: INFO
  file: logs/app.log
```

### .env

```bash
# 管理后台密码
ADMIN_PASS=your_secure_password

# 其他环境变量
# PYTHONPATH=./src
```

---

## 📡 API 接口

| 接口 | 方法 | 说明 |
|:-----|:-----|:-----|
| `/api/parse` | POST | 解析链接，返回视频/图片信息 |
| `/api/stream` | GET | 流式播放视频（支持 Range） |
| `/api/download` | POST | 下载文件 |
| `/admin` | GET | 管理后台 |
| `/admin/login` | POST | 管理员登录 |

### 示例

```bash
# 解析视频
curl -X POST http://localhost:8001/api/parse \
  -H "Content-Type: application/json" \
  -d '{"url": "https://v.douyin.com/xxx"}'

# 下载视频
curl -X POST http://localhost:8001/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://v.douyin.com/xxx", "quality": "1080p"}' \
  --output video.mp4
```

---

## 🛠️ 开发指南

### 快捷命令

```bash
make help       # 显示所有命令
make install    # 安装依赖
make dev        # 安装开发依赖
make test       # 运行测试
make lint       # 代码检查
make format     # 格式化代码
make check      # 完整检查（lint + format + test）
make run        # 运行开发服务器
make clean      # 清理临时文件
```

### 代码质量

```bash
# Ruff 检查 + 格式化
ruff check src/
ruff format src/

# pytest 测试
pytest tests/

# pre-commit 钩子
pre-commit install
pre-commit run --all-files
```

### 添加新平台

1. 在 `downloader.py` 添加平台检测函数
2. 实现 `_extract_xxx()` 解析函数
3. 在 `extract_video_info()` 中添加路由
4. 更新 `ALLOWED_DOMAINS` 白名单
5. 添加测试用例

---

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_config.py
pytest tests/test_utils.py

# 带覆盖率
pytest --cov=src/douyin_downloader
```

---

## 📦 依赖说明

### 核心依赖

| 包 | 用途 |
|:---|:-----|
| `fastapi` | Web 框架 |
| `uvicorn` | ASGI 服务器 |
| `httpx` | HTTP 客户端 |
| `pydantic` | 数据验证 |
| `PyYAML` | 配置文件解析 |

### 功能依赖

| 包 | 用途 |
|:---|:-----|
| `f2` | 抖音 API 库 |
| `TikTokApi` | TikTok API 库 |
| `playwright` | 浏览器自动化（图文解析） |

### 开发依赖

| 包 | 用途 |
|:---|:-----|
| `pytest` | 测试框架 |
| `ruff` | Lint + Format |
| `pre-commit` | Git 钩子 |

---

## 🚢 部署

### Docker

```bash
# 构建镜像
docker build -t douyin-downloader .

# 运行容器
docker run -d -p 8001:8001 --name downloader douyin-downloader
```

### 传统部署

```bash
# 安装依赖
pip install -r requirements.txt
pip install -e .

# 运行
uvicorn src.douyin_downloader.main:app --host 0.0.0.0 --port 8001
```

详细部署文档见 [docs/DEPLOY.md](docs/DEPLOY.md)

---

## 🔒 安全说明

- **URL 白名单** — 防止 SSRF 攻击
- **Cookie 保护** — 敏感信息不提交到 Git
- **CORS 配置** — 限制跨域访问
- **输入验证** — Pydantic 数据校验

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -m 'Add feature xxx'`)
4. 推送分支 (`git push origin feature/xxx`)
5. 创建 Pull Request

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

## 🙏 致谢

- [f2](https://github.com/Johnserf-Seed/f2) — 抖音 API 库
- [FastAPI](https://fastapi.tiangolo.com/) — Web 框架
- [Tailwind CSS](https://tailwindcss.com/) — CSS 框架
- [GSAP](https://greensock.com/gsap/) — 动画库

---

## 📧 联系

- Issues: [GitHub Issues](https://github.com/f3271174706-tech/SalaryMeow-Downloader/issues)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！**

</div>
