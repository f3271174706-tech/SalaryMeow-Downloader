#!/bin/bash
# 项目初始化脚本（Linux/macOS）

set -e

echo "=========================================="
echo "初始化 SalaryMeow Downloader..."
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
python -m pip install -e ".[dev,full]"
echo "依赖安装完成"

# 安装 Playwright（可选）
echo ""
echo "安装 Playwright 浏览器..."
python -m playwright install chromium 2>/dev/null || echo "Playwright 安装跳过"

# 创建必要的目录
echo ""
echo "创建必要的目录..."
mkdir -p data logs downloads

# 创建本地配置文件
echo ""
echo "检查 config.yaml 文件..."
if [ -f "config.yaml" ]; then
    echo "config.yaml 已存在"
else
    cp config.yaml.example config.yaml
    echo "已从 config.yaml.example 创建 config.yaml"
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
echo "2. 编辑 config.yaml"
echo "3. 运行项目: python -m uvicorn douyin_downloader.main:app --host 0.0.0.0 --port 8001 --reload"
echo "4. 运行测试: pytest"
echo ""
echo "开始开发吧！"
