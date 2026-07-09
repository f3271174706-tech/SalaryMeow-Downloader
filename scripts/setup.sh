#!/bin/bash
# 项目初始化脚本（Linux/macOS）

set -e

echo "=========================================="
echo "初始化 douyin-downloader 项目..."
echo "=========================================="

# 检查 Python 版本
echo "检查 Python 版本..."
python_version=$(python3 --version 2>&1)
echo "Python 版本: $python_version"

# 创建虚拟环境
echo ""
echo "创建虚拟环境..."
if [ -d ".venv" ]; then
    echo "虚拟环境已存在，跳过创建"
else
    python3 -m venv .venv
    echo "虚拟环境创建成功"
fi

# 激活虚拟环境
echo ""
echo "激活虚拟环境..."
source .venv/bin/activate

# 升级 pip
echo ""
echo "升级 pip..."
pip install --upgrade pip setuptools wheel

# 安装项目依赖
echo ""
echo "安装项目依赖..."
pip install -r requirements.txt
pip install -e .
echo "依赖安装完成"

# 安装开发依赖
echo ""
echo "安装开发依赖..."
pip install -e ".[dev]" 2>/dev/null || echo "开发依赖安装跳过"

# 安装 Playwright（可选）
echo ""
echo "安装 Playwright 浏览器..."
python -m playwright install chromium 2>/dev/null || echo "Playwright 安装跳过"

# 创建必要的目录
echo ""
echo "创建必要的目录..."
mkdir -p data logs downloads

# 创建 .env 文件
echo ""
echo "检查 .env 文件..."
if [ -f ".env" ]; then
    echo ".env 文件已存在"
else
    echo "创建 .env 文件..."
    cat > .env << EOF
ADMIN_USER=admin
ADMIN_PASS=$(openssl rand -hex 32)
DIRECT_INVITE_CODE=
DEBUG=False
EOF
    echo ".env 文件创建成功"
fi

# 初始化 Git
echo ""
echo "初始化 Git..."
if [ -d ".git" ]; then
    echo "Git 仓库已存在，跳过初始化"
else
    git init
    echo "Git 仓库初始化成功"
fi

echo ""
echo "=========================================="
echo "项目初始化完成！"
echo "=========================================="
echo ""
echo "后续步骤："
echo "1. 激活虚拟环境: source .venv/bin/activate"
echo "2. 编辑 config.yaml 配置 Cookie"
echo "3. 运行项目: make run"
echo "4. 运行测试: make test"
echo ""
echo "开始开发吧！"
