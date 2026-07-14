.PHONY: help install dev test lint format check clean run

help:  ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## 安装项目依赖
	pip install --upgrade pip setuptools wheel
	pip install -r requirements.txt
	pip install -e .

dev:  ## 安装开发依赖
	pip install --upgrade pip setuptools wheel
	pip install -e ".[dev]"
	pre-commit install

full:  ## 安装完整依赖（含 API 库）
	pip install --upgrade pip setuptools wheel
	pip install -e ".[full,dev]"
	python -m playwright install chromium
	pre-commit install

test:  ## 运行测试
	pytest

test-cov:  ## 运行测试并生成覆盖率报告
	pytest --cov=src --cov-report=html --cov-report=term

lint:  ## 运行代码检查
	ruff check .

format:  ## 格式化代码
	ruff format .
	ruff check --fix .

check:  ## 检查代码质量（lint + format + test）
	ruff check .
	ruff format --check .
	pytest

clean:  ## 清理临时文件
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ htmlcov/ .coverage

run:  ## 运行开发服务器
	python -m uvicorn douyin_downloader.main:app --host 0.0.0.0 --port 8001 --reload

setup:  ## 初始化项目（创建 venv + 安装依赖）
	python -m venv .venv
	@echo "虚拟环境已创建，请激活："
	@echo "  Windows PowerShell: .\\.venv\\Scripts\\Activate.ps1"
	@echo "  Linux/macOS: source .venv/bin/activate"
