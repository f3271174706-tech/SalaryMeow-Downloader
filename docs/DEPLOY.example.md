# SalaryMeow Downloader 通用部署示例

本文只说明通用流程。请用自己的目录、服务账号和域名替换尖括号占位符；不要把服务器地址、私钥、Cookie、密码或邀请码写入仓库。

## 1. 准备运行环境

要求 Python 3.9 或更高版本。可选解析能力还可能需要 FFmpeg 和 Playwright Chromium。

```bash
cd <project-directory>
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[full]"
python -m playwright install chromium
cp config.yaml.example config.yaml
```

编辑未受 Git 跟踪的 `config.yaml`。生产环境至少应设置管理员密码，并按需设置邀请码、Cookie、CORS 来源和 `network.proxy`。

## 2. 先以前台方式验证

```bash
python -m uvicorn douyin_downloader.main:app --host 0.0.0.0 --port 8001
```

确认首页、`POST /api/parse`、下载和管理员登录均符合预期后，再配置进程管理器。

## 3. 使用 systemd 托管（示例）

创建仅存在于服务器上的服务文件，并替换全部占位符：

```ini
[Unit]
Description=SalaryMeow Downloader
After=network.target

[Service]
Type=simple
User=<service-user>
WorkingDirectory=<project-directory>
ExecStart=<project-directory>/.venv/bin/python -m uvicorn douyin_downloader.main:app --host 127.0.0.1 --port 8001
Restart=on-failure
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

重新加载服务管理器、启动服务并检查日志。服务文件中不要内嵌密码或 Cookie；如需环境变量，请使用权限受限且不进入仓库的环境文件。

## 4. 配置反向代理（示例）

将公网 HTTPS 请求转发到应用监听端口，并保留常用代理头。以下片段中的域名必须替换：

```nginx
server {
    listen 443 ssl;
    server_name <domain>;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

TLS 证书、域名解析、防火墙和日志保留策略应按你的平台规范单独配置。

## 5. 从根目录旧入口迁移

如果现有服务仍启动 `main:app`，先不要删除根目录的重复代码。推荐流程：

1. 在独立端口启动 `douyin_downloader.main:app`。
2. 对首页、三套 UI、解析、Range 流式响应、下载、管理员登录和邀请码进行回归测试。
3. 将服务管理器的应用入口改为 `douyin_downloader.main:app`，重启并观察日志。
4. 确认线上流量稳定后，再在后续变更中移除根目录重复实现。

## 6. 更新与回滚

更新前备份服务器私有配置并记录当前版本。更新代码后重新安装依赖、运行测试，再重启服务。回滚时恢复上一已验证版本及其兼容配置；不要把服务器备份复制回 Git 仓库。
