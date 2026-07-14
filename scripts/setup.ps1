# 项目初始化脚本（Windows PowerShell）

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "初始化 SalaryMeow Downloader..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 检查 Python 版本
Write-Host ""
Write-Host "检查 Python 版本..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python 版本: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "错误: 未找到 Python，请先安装 Python" -ForegroundColor Red
    exit 1
}

# 创建虚拟环境
Write-Host ""
Write-Host "创建虚拟环境..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "虚拟环境已存在，跳过创建" -ForegroundColor Green
} else {
    python -m venv .venv
    Write-Host "虚拟环境创建成功" -ForegroundColor Green
}

# 激活虚拟环境
Write-Host ""
Write-Host "激活虚拟环境..." -ForegroundColor Yellow
.\.venv\Scripts\Activate.ps1

# 升级 pip
Write-Host ""
Write-Host "升级 pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip setuptools wheel

# 安装项目依赖
Write-Host ""
Write-Host "安装项目依赖..." -ForegroundColor Yellow
python -m pip install -e ".[dev,full]"
Write-Host "依赖安装完成" -ForegroundColor Green

# 创建必要的目录
Write-Host ""
Write-Host "创建必要的目录..." -ForegroundColor Yellow
@("data", "logs", "downloads") | ForEach-Object {
    New-Item -ItemType Directory -Force -Path $_ | Out-Null
}
Write-Host "目录创建完成" -ForegroundColor Green

# 创建本地配置文件
Write-Host ""
Write-Host "检查 config.yaml 文件..." -ForegroundColor Yellow
if (Test-Path "config.yaml") {
    Write-Host "config.yaml 已存在" -ForegroundColor Green
} else {
    Copy-Item "config.yaml.example" "config.yaml"
    Write-Host "已从 config.yaml.example 创建 config.yaml" -ForegroundColor Green
}

# 初始化 Git
Write-Host ""
Write-Host "初始化 Git..." -ForegroundColor Yellow
if (Test-Path ".git") {
    Write-Host "Git 仓库已存在，跳过初始化" -ForegroundColor Green
} else {
    git init
    Write-Host "Git 仓库初始化成功" -ForegroundColor Green
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "项目初始化完成！" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "后续步骤：" -ForegroundColor White
Write-Host "1. 激活虚拟环境: .\.venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "2. 编辑 config.yaml" -ForegroundColor White
Write-Host "3. 运行项目: python -m uvicorn douyin_downloader.main:app --host 0.0.0.0 --port 8001 --reload" -ForegroundColor White
Write-Host "4. 运行测试: pytest" -ForegroundColor White
Write-Host ""
Write-Host "开始开发吧！" -ForegroundColor Green
