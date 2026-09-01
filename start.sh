#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
    echo "请先复制 .env.example 为 .env 并填写本地配置"
    exit 1
fi
if [ ! -x .venv/bin/python ]; then
    echo "未找到项目虚拟环境，请先运行 python -m uv sync --group dev"
    exit 1
fi
mkdir -p logs

echo "主应用：http://127.0.0.1:9901"
echo "默认不启动 Shopify/Ads MCP；Agent 使用进程内只读 Shopify 工具。"
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn app.main:app \
    --host "${HOST:-127.0.0.1}" \
    --port "${PORT:-9901}" \
    --log-level info
