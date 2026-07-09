# 部署文档（私密）

## 服务器

| 项 | 值 |
|----|-----|
| 实例 IP | 103.236.92.6 |
| 远程地址 | 103.236.92.3:51918（厂商公网地址） |
| SSH 端口 | 51918 |
| 登录 | `ssh root@103.236.92.6 -p 51918` |
| 密钥 | `C:\Users\32711\.ssh\id_ed25519`（Ed25519，仅密钥登录） |
| 公钥 | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEIGd9+rBtIQ0wnJ1MYSjqVHJvi/juU980GFSGF90D2K 32711@A7` |
| 代理 | `http://127.0.0.1:7890`（mihomo） |
| 规格 | Ubuntu 24.04 / 4核4G / 29G SSD |

## 项目目录

| 项目 | 路径 | 服务名 | 端口 |
|------|------|--------|------|
| SalaryMeow Downloader | `/root/DOWN/` | douyin-dl | 9000 |

## Cloudflare Tunnel

本地配置方式运行（非 Zero Trust 仪表盘管理）。

### fzpnowm.top（Tunnel: `255822ac`）

```bash
# 配置文件
cat /root/.cloudflared/fzpnowm.yml
# 服务
systemctl status cloudflared-fzpnowm
# 日志
journalctl -u cloudflared-fzpnowm --no-pager -n 20
```

### fzp.me（已停用）

fzp.me 项目已合并到 fzpnowm.top，隧道已停用。

### 重启规则

`Restart=on-failure` + `RestartSec=5`。

| 场景 | 自动恢复 | 说明 |
|------|:--------:|------|
| 进程崩溃/异常退出 | ✅ | systemd `Restart=on-failure` |
| Edge 波动（进程存活但隧道不通） | ✅ | crontab 每 5 分钟 `check-tunnels.sh` |
| 服务器重启 | ✅ | systemd 开机自启 |
| 修改 config 或 credentials 后 | ❌ | 手动 `systemctl restart` |

手动重启：
```bash
systemctl restart cloudflared-fzpnowm
```

## 健康检查

脚本：`/root/check-tunnels.sh`
Crontab：`*/5 * * * *`
日志：`/var/log/check-tunnels.log`

四层检查：
1. mihomo 代理存活 → `systemctl is-active mihomo` → 挂了重启
2. Tunnel 进程存活 → `systemctl is-active cloudflared-fzpnowm` → 挂了重启
3. 本地后端存活 → `curl localhost:9000` → 挂了重启并 wait 5s
4. 域名公网可达 → `curl https://fzpnowm.top` → 后端正常但域名不通 → 重启 tunnel

## 下载文件自动清理

脚本：`/root/cleanup-downloads.sh`
Crontab：`0 * * * *`（每小时整点）
日志：`/var/log/cleanup-downloads.log`

清理目录（超过 60 分钟的文件）：

| 项目 | 目录 |
|------|------|
| SalaryMeow Downloader | `/root/DOWN/downloads/` |

手动执行：`/root/cleanup-downloads.sh`

## 服务管理

```bash
# 后端服务
systemctl restart douyin-dl
journalctl -u douyin-dl --no-pager -n 30

# mihomo 代理
systemctl restart mihomo
journalctl -u mihomo --no-pager -n 20

# 重启后验证
curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/
```

## 从本地上传文件

```bash
# 代码文件
scp -P 51918 "d:/mycode/douyin-downloader 3.0/main.py" root@103.236.92.6:/root/DOWN/
scp -P 51918 "d:/mycode/douyin-downloader 3.0/downloader.py" root@103.236.92.6:/root/DOWN/
scp -P 51918 "d:/mycode/douyin-downloader 3.0/douyin_api.py" root@103.236.92.6:/root/DOWN/
scp -P 51918 "d:/mycode/douyin-downloader 3.0/config.py" root@103.236.92.6:/root/DOWN/
scp -P 51918 "d:/mycode/douyin-downloader 3.0/config.yaml" root@103.236.92.6:/root/DOWN/
scp -P 51918 "d:/mycode/douyin-downloader 3.0/utils.py" root@103.236.92.6:/root/DOWN/

# 静态文件
scp -P 51918 "d:/mycode/douyin-downloader 3.0/static/index.html" root@103.236.92.6:/root/DOWN/static/
```

## API 库安装

```bash
# 安装 f2（抖音 API）
pip3 install f2 --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 TikTokApi（TikTok API）
pip3 install TikTokApi --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装 Playwright 浏览器
python3 -m playwright install chromium
# 安装 Chromium 依赖
apt-get install -y libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64
```

## Cookie 配置（多 Cookie 随机选择）

编辑 `/root/DOWN/config.yaml` 配置 Cookie（支持多个，随机选择）：

```yaml
cookies:
  douyin:
    - "抖音Cookie1"
    - "抖音Cookie2"  # 可以添加多个
  tiktok:
    - "TikTokCookie"
  bilibili:
    - ""  # 可选，提高清晰度
  twitter:
    - ""  # 可选
  kuaishou:
    - ""  # 可选
```

获取 Cookie 方法：
1. 浏览器打开对应网站并登录
2. F12 打开开发者工具 → Network
3. 刷新页面，点击任意请求
4. 复制 Request Headers 中的 Cookie 值

## 管理后台

访问 `https://fzpnowm.top/admin` 查看解析记录（Liquid Glass 风格，需登录）。

### 环境变量配置

在 systemd 服务中添加：

```ini
Environment=ADMIN_USER=admin
Environment=ADMIN_PASS=your_password
```

### 安全特性

| 特性 | 说明 |
|:---|:---|
| 登录失败限制 | 5 次失败后锁定 15 分钟 |
| Session 签名 | HMAC-SHA256 |
| Cookie 安全 | httponly + SameSite=Lax + secure |
| 过期时间 | 24 小时自动过期 |

### 功能

- 统计卡片（各平台解析数量）
- 按平台/类型筛选
- 搜索标题
- 点击链接复制并展开（10秒后收起）

## mihomo 代理

用于访问 Twitter/X 和 TikTok（中国大陆服务器需要代理）。

```bash
# 配置文件
cat /etc/mihomo/config.yaml
# 服务
systemctl status mihomo
# 日志
journalctl -u mihomo --no-pager -n 20
# API
curl http://127.0.0.1:9090/proxies/Auto  # 查看当前节点
```

- 代理端口：`127.0.0.1:7890`（HTTP + SOCKS5）
- 节点选择：`url-test` 自动选最快节点
- 订阅更新：每小时自动拉取
- 健康检查：每 600 秒检测节点可用性

### 代理规则

| 域名 | 规则 | 说明 |
|:---|:---|:---|
| `douyinvod.com` | DIRECT | 抖音视频 CDN |
| `douyinpic.com` | DIRECT | 抖音图片 CDN |
| `snssdk.com` | DIRECT | 抖音 API |
| `bilibili.com` | DIRECT | B站 |
| `twitter.com` | Proxy | Twitter |
| `tiktok.com` | Proxy | TikTok |
| 其他 | DIRECT | 默认直连 |

手动切换节点：
```bash
curl -s -X PUT http://127.0.0.1:9090/proxies/Auto -H 'Content-Type: application/json' -d '{"name": "节点名称"}'
```

## SSH 安全

- 密码登录已禁用：`PasswordAuthentication no`
- Root 仅密钥登录：`PermitRootLogin prohibit-password`
- 暴力破解来源已阻断（曾来自 `218.71.38.151`）

```bash
# 查看最近 SSH 攻击
journalctl -u sshd --no-pager -p err -n 20
```

## 修复记录

### 2026-06-10 · Project 2 上线与修复

- 新建 fzp.me 隧道（`6ba4df3f`，本地 config 方式），废弃旧 FZP-ME-2
- 静态文件上传：`bg.png`, `bg2.jpg`, `bg3.png`, `html2canvas.min.js`, `liquidGL.js`
- 修复 `liquidGL is not defined`：移除 JS 脚本的 `defer` 属性
- 静态资源加 `?v=2` 破除浏览器缓存
- `server_patches.py` 应用到 Project 2 的 `downloader.py`
- SSH 禁用密码登录，仅密钥认证
- 更新 `check-tunnels.sh`：增加域名可达性检查和防误判逻辑

### 2026-06-11 · 代码审查修复

- **下载文件自动清理**：新增 `/root/cleanup-downloads.sh`，crontab 每小时清理超过 60 分钟的下载文件
- **Project 2 幻灯片修复**：`_make_slides_video` 从单图循环改为全图片逐张拼接（移植自 Project 1）
- **Project 2 Twitter 下载回退**：新增 `_download_twitter_video`，直链失败自动走 m3u8/ffmpeg（解决服务端 `video.twimg.com` 被封）
- **Project 1 死代码清理**：删除未使用的 `_extract_ytdlp` 及 `yt-dlp` 导入
- **流式代理 + Range 支持**：`/api/stream` 改为 httpx 流式代理（边下边传），传递浏览器 Range 头返回 206，支持拖进度条；m3u8 仍走先下载后返回；超时设为 connect=10s, read=300s

### 2026-06-26 · 服务器迁移

- 旧服务器 `103.236.88.224` 被机房回收，迁移到新服务器 `103.236.92.6`
- SSH 端口改为 51918，仅密钥登录
- 重新部署所有服务：douyin-dl、cloudflared 隧道、mihomo 代理
- fzp.me 项目合并到 fzpnowm.top，fzp.me 隧道停用
- 安装 mihomo v1.19.8，配置 url-test 自动选择最快节点
- 健康检查增加 mihomo 代理存活检查

### 2026-06-28 · API 模式与性能优化

#### 新增功能
- **抖音 API 模式**：使用 f2 库解析动图（live_photo），速度 1-3 秒
- **TikTok API 模式**：使用 TikTokApi 库解析 TikTok 视频/图片
- **配置模块**：新增 config.py、config.yaml、utils.py
- **Cookie 支持**：抖音、TikTok Cookie 配置，提高解析成功率

#### 性能优化
- **浏览器池**：Playwright 浏览器实例复用，省去启动时间
- **并行下载**：多张图片/视频片段并行下载，总时间 = 最慢的那张
- **代理规则优化**：国内 CDN 直连，国外走代理

#### 修复
- **Playwright 依赖**：安装 Chromium 依赖库（libnspr4 等）
- **asyncio 冲突**：使用 ThreadPoolExecutor 避免 FastAPI 事件循环冲突
- **代理配置**：TikTokApi 添加代理支持

#### 文件变更
- 新增：`douyin_api.py`、`config.py`、`config.yaml`、`utils.py`
- 修改：`downloader.py`、`main.py`
- 删除：`server_patches.py`（已废弃）

#### 各平台解析方式

| 平台 | 解析方式 | 速度 |
|:---|:---|:---|
| 抖音视频/图片 | HTML 解析 | <1 秒 |
| 抖音动图 | f2 API | 1-3 秒 |
| Twitter/X | fxtwitter API | 1-2 秒 |
| TikTok | TikTokApi + ssstiktok | 5-10 秒 |
| B站 | HTML 解析 | <1 秒 |
| 快手 | HTML 解析 | <1 秒 |

## SSH 密钥对

### 私钥（`~/.ssh/id_ed25519`）

```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBCBnffqwbSENMJydTGEo6lRyb4v47lPfNBhUhhfdA9igAAAJDpfa+Y6X2v
mAAAAAtzc2gtZWQyNTUxOQAAACBCBnffqwbSENMJydTGEo6lRyb4v47lPfNBhUhhfdA9ig
AAAEDl5WRZJ0vTjTIyC4ZOdW03TTIMzXPCfpshetY75S39u0IGd9+rBtIQ0wnJ1MYSjqVH
Jvi/juU980GFSGF90D2KAAAACDMyNzExQEE3AQIDBAU=
-----END OPENSSH PRIVATE KEY-----
```

### 公钥

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEIGd9+rBtIQ0wnJ1MYSjqVHJvi/juU980GFSGF90D2K 32711@A7
```

> ⚠️ 此文件已在 `.gitignore` 中，不会被提交到 GitHub。

---

# 部署指南

## 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
python -m playwright install chromium

# 启动服务（默认端口 8001）
python main.py

# 访问
# v3 白色液态玻璃: http://127.0.0.1:8001
# v1 经典暗色: http://127.0.0.1:8001/v1
# v2 WebGL 玻璃: http://127.0.0.1:8001/v2
```

## 文件结构

```
DOWN/
├── main.py          FastAPI 路由 + 流式代理
├── downloader.py    核心下载引擎
├── douyin_api.py    API 模式（f2 + TikTokApi）
├── config.py        配置管理模块
├── config.yaml      配置文件（Cookie、代理等）
├── utils.py         工具函数
├── requirements.txt 依赖列表
├── static/          前端静态文件
├── downloads/       临时下载目录（自动清理）
├── DEPLOY.md        部署文档
└── README.md        项目说明
```

## 快速启动

```bash
# 1. 克隆项目
git clone <仓库地址>
cd douyin-downloader

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright
python -m playwright install chromium

# 4. 配置 Cookie（可选但推荐）
# 编辑 config.yaml，填入抖音/TikTok Cookie

# 5. 启动服务
python main.py
```

## 配置说明

### Cookie 配置

编辑 `config.yaml`：

```yaml
cookies:
  douyin: "你的抖音Cookie"  # 必须，提高解析成功率
  tiktok: "你的TikTokCookie"  # 可选，TikTok API 需要
```

### 代理配置

如果需要访问 Twitter/TikTok（国内服务器）：

```yaml
network:
  proxy: "http://127.0.0.1:7890"  # 代理地址
```

### API 模式配置

```yaml
api:
  enabled: true  # 是否启用 API 模式
  timeout: 10    # API 超时（秒）
```

## 常用命令

```bash
# 启动服务
python main.py

# 后台运行
nohup python main.py > /dev/null 2>&1 &

# 使用 systemd（推荐）
systemctl start douyin-dl
systemctl restart douyin-dl
systemctl status douyin-dl

# 查看日志
journalctl -u douyin-dl -f
```

## 故障排查

| 问题 | 解决方案 |
|:---|:---|
| 解析失败 | 检查 Cookie 是否过期 |
| 视频下载慢 | 检查代理配置 |
| 动图解析失败 | 检查 Playwright 是否安装 |
| 服务启动失败 | 检查端口是否被占用 |

---

# 新服务器从零搭建教程

## 1. 系统要求

| 项目 | 最低配置 | 推荐配置 |
|:---|:---|:---|
| 系统 | Ubuntu 20.04+ | Ubuntu 24.04 LTS |
| CPU | 2 核 | 4 核 |
| 内存 | 2 GB | 4 GB |
| 硬盘 | 20 GB | 30 GB SSD |
| 网络 | 公网 IP | 公网 IP + 代理 |

## 2. 初始化服务器

```bash
# 更新系统
apt update && apt upgrade -y

# 安装基础工具
apt install -y curl wget git vim ufw fail2ban

# 设置时区
timedatectl set-timezone Asia/Shanghai
```

## 3. 安装 Python 环境

```bash
# 安装 Python 3.12
apt install -y python3 python3-pip python3-venv

# 验证版本
python3 --version  # 应该是 3.12+

# 配置 pip 镜像（加速下载）
mkdir -p ~/.pip
cat > ~/.pip/pip.conf << 'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
EOF
```

## 4. 安装项目依赖

```bash
# 创建项目目录
mkdir -p /root/DOWN
cd /root/DOWN

# 安装 Python 依赖
pip3 install --break-system-packages \
    fastapi \
    uvicorn \
    httpx \
    f2 \
    TikTokApi \
    playwright \
    pyyaml \
    pydantic
```

## 5. 安装 Playwright 浏览器

```bash
# 安装 Chromium 浏览器
python3 -m playwright install chromium

# 安装 Chromium 依赖库
apt install -y \
    libnspr4 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64

# 验证安装
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

## 6. 安装 ffmpeg

```bash
apt install -y ffmpeg
ffmpeg -version
```

## 7. 上传项目文件

从本地上传所有项目文件到服务器：

```bash
# 在本地执行（替换为你的服务器 IP 和端口）
scp -P 51918 \
    d:/mycode/douyin-downloader 3.0/main.py \
    d:/mycode/douyin-downloader 3.0/downloader.py \
    d:/mycode/douyin-downloader 3.0/douyin_api.py \
    d:/mycode/douyin-downloader 3.0/config.py \
    d:/mycode/douyin-downloader 3.0/config.yaml \
    d:/mycode/douyin-downloader 3.0/utils.py \
    d:/mycode/douyin-downloader 3.0/requirements.txt \
    root@你的服务器IP:/root/DOWN/

# 上传静态文件
scp -P 51918 -r \
    d:/mycode/douyin-downloader 3.0/static/ \
    root@你的服务器IP:/root/DOWN/
```

## 8. 配置 Cookie

编辑 `/root/DOWN/config.yaml`，填入各平台 Cookie：

```yaml
cookies:
  # 抖音 Cookie（必须，提高解析成功率）
  douyin: "你的抖音Cookie"
  # TikTok Cookie（可选，TikTok API 需要）
  tiktok: "你的TikTokCookie"
  # B站 Cookie（可选，提高视频清晰度）
  bilibili: ""
  # Twitter/X Cookie（可选）
  twitter: ""
```

**获取 Cookie 方法：**
1. 浏览器打开对应网站并登录
2. F12 打开开发者工具 → Network
3. 刷新页面，点击任意请求
4. 复制 Request Headers 中的 Cookie 值

## 9. 配置代理（可选）

如果服务器在国内，需要代理访问 Twitter/TikTok。

编辑 `/root/DOWN/config.yaml`：

```yaml
network:
  # 代理地址（留空则不走代理）
  proxy: "http://127.0.0.1:7890"
```

### 安装 mihomo 代理（可选）

```bash
# 下载 mihomo
wget https://github.com/MetaCubeX/mihomo/releases/download/v1.19.8/mihomo-linux-amd64-v1.19.8.gz
gunzip mihomo-linux-amd64-v1.19.8.gz
chmod +x mihomo-linux-amd64-v1.19.8
mv mihomo-linux-amd64-v1.19.8 /usr/local/bin/mihomo

# 创建配置目录
mkdir -p /etc/mihomo

# 创建配置文件（需要替换为你的订阅链接）
cat > /etc/mihomo/config.yaml << 'EOF'
mixed-port: 7890
allow-lan: false
bind-address: "127.0.0.1"
mode: rule
log-level: info
external-controller: 127.0.0.1:9090

proxy-providers:
  my-sub:
    type: http
    url: "你的订阅链接"
    interval: 3600
    path: ./providers/sub.yaml
    health-check:
      enable: true
      interval: 600
      url: http://www.gstatic.com/generate_204

proxy-groups:
  - name: Auto
    type: url-test
    use:
      - my-sub
    url: http://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50

  - name: Proxy
    type: select
    proxies:
      - Auto
      - DIRECT

rules:
  # 国内 CDN 直连
  - DOMAIN-SUFFIX,douyinvod.com,DIRECT
  - DOMAIN-SUFFIX,douyinpic.com,DIRECT
  - DOMAIN-SUFFIX,snssdk.com,DIRECT
  - DOMAIN-SUFFIX,bilibili.com,DIRECT
  - DOMAIN-SUFFIX,bilivideo.com,DIRECT
  # 国外服务走代理
  - DOMAIN-SUFFIX,twitter.com,Proxy
  - DOMAIN-SUFFIX,x.com,Proxy
  - DOMAIN-SUFFIX,tiktok.com,Proxy
  # 其他直连
  - MATCH,DIRECT
EOF

# 创建 systemd 服务
cat > /etc/systemd/system/mihomo.service << 'EOF'
[Unit]
Description=mihomo Proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mihomo -d /etc/mihomo
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
systemctl daemon-reload
systemctl enable mihomo
systemctl start mihomo

# 验证
systemctl status mihomo
curl -x http://127.0.0.1:7890 https://www.google.com -o /dev/null -w '%{http_code}'
```

## 10. 配置后端服务

```bash
# 创建 systemd 服务文件
cat > /etc/systemd/system/douyin-dl.service << 'EOF'
[Unit]
Description=Douyin Downloader API
After=network.target mihomo.service

[Service]
Type=simple
WorkingDirectory=/root/DOWN
Environment=HTTP_PROXY=http://127.0.0.1:7890
Environment=HTTPS_PROXY=http://127.0.0.1:7890
ExecStart=/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 9000
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
systemctl daemon-reload
systemctl enable douyin-dl
systemctl start douyin-dl

# 验证
systemctl status douyin-dl
curl -s http://localhost:9000/ | head -5
```

## 11. 配置防火墙

```bash
# 启用防火墙
ufw enable

# 允许 SSH
ufw allow 22/tcp

# 允许后端端口（如果需要直连）
ufw allow 9000/tcp

# 查看状态
ufw status
```

## 12. 配置 Cloudflare Tunnel（推荐）

使用 Cloudflare Tunnel 暴露服务，无需开放端口。

```bash
# 安装 cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# 登录（会生成证书）
cloudflared tunnel login

# 创建隧道
cloudflared tunnel create my-tunnel

# 配置文件
cat > /root/.cloudflared/config.yml << 'EOF'
tunnel: 你的隧道ID
credentials-file: /root/.cloudflared/你的隧道ID.json

ingress:
  - hostname: 你的域名.com
    service: http://localhost:9000
  - service: http_status:404
EOF

# 创建 systemd 服务
cat > /etc/systemd/system/cloudflared.service << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
systemctl daemon-reload
systemctl enable cloudflared
systemctl start cloudflared

# 验证
systemctl status cloudflared
curl https://你的域名.com -o /dev/null -w '%{http_code}'
```

## 13. 健康检查（可选）

```bash
# 创建健康检查脚本
cat > /root/check-tunnels.sh << 'EOF'
#!/bin/bash
LOG="/var/log/check-tunnels.log"

# 检查 mihomo
if ! systemctl is-active -q mihomo; then
    echo "$(date) - mihomo is down, restarting..." >> $LOG
    systemctl restart mihomo
fi

# 检查后端
if ! curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/ | grep -q 200; then
    echo "$(date) - Backend is down, restarting..." >> $LOG
    systemctl restart douyin-dl
    sleep 5
fi

# 检查 Tunnel
if ! systemctl is-active -q cloudflared; then
    echo "$(date) - Tunnel is down, restarting..." >> $LOG
    systemctl restart cloudflared
fi
EOF

chmod +x /root/check-tunnels.sh

# 添加 crontab（每 5 分钟检查一次）
(crontab -l 2>/dev/null; echo "*/5 * * * * /root/check-tunnels.sh") | crontab -
```

## 14. 自动清理下载文件（可选）

```bash
# 创建清理脚本
cat > /root/cleanup-downloads.sh << 'EOF'
#!/bin/bash
LOG="/var/log/cleanup-downloads.log"
DIR="/root/DOWN/downloads"

echo "$(date) - Cleaning up files older than 60 minutes..." >> $LOG
find $DIR -type f -mmin +60 -delete -print | wc -l | xargs -I {} echo "Removed {} files" >> $LOG
EOF

chmod +x /root/cleanup-downloads.sh

# 添加 crontab（每小时清理一次）
(crontab -l 2>/dev/null; echo "0 * * * * /root/cleanup-downloads.sh") | crontab -
```

## 15. 验证部署

```bash
# 检查所有服务状态
systemctl status douyin-dl
systemctl status mihomo
systemctl status cloudflared

# 测试解析功能
curl -s -X POST http://localhost:9000/api/parse \
  -H "Content-Type: application/json" \
  -d '{"url":"https://v.douyin.com/T5T4Ii7ce7c/"}' | python3 -m json.tool

# 测试外部访问
curl https://你的域名.com -o /dev/null -w '%{http_code}'
```

## 16. 常用命令

```bash
# 查看日志
journalctl -u douyin-dl -f
journalctl -u mihomo -f
journalctl -u cloudflared -f

# 重启服务
systemctl restart douyin-dl
systemctl restart mihomo
systemctl restart cloudflared

# 更新代码后重启
scp -P 51918 downloader.py root@服务器:/root/DOWN/
ssh -p 51918 root@服务器 "systemctl restart douyin-dl"

# 切换代理节点
curl -s -X PUT http://127.0.0.1:9090/proxies/Auto \
  -H 'Content-Type: application/json' \
  -d '{"name": "🇯🇵日本01|流媒体解锁"}'
```
