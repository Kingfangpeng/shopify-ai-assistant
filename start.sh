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

vector_configured=true
if ! grep -Eq '^MINIO_ROOT_USER=.+$' .env || grep -Eq '^MINIO_ROOT_USER=replace-with' .env; then
    vector_configured=false
fi
if ! grep -Eq '^MINIO_ROOT_PASSWORD=.+$' .env || grep -Eq '^MINIO_ROOT_PASSWORD=replace-with' .env; then
    vector_configured=false
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "[提示] Docker 未运行，知识库问答暂不可用；启动 Docker 后重新运行本脚本。"
elif [ "$vector_configured" != true ]; then
    echo "[提示] .env 缺少随机 MINIO_ROOT_USER / MINIO_ROOT_PASSWORD，请参考 .env.example 补齐。"
else
    echo "正在启动本地 Milvus 与 MinIO..."
    docker compose -f vector-database.yml up -d --wait --wait-timeout 180 || echo "[提示] 向量数据库启动失败，聊天页会显示具体依赖错误。"
fi

echo "主应用：http://127.0.0.1:9901"
echo "默认不启动 Shopify/Ads MCP；Agent 使用进程内只读 Shopify 工具。"
.venv/bin/alembic upgrade head
.venv/bin/python -m uvicorn app.main:app \
    --host "${HOST:-127.0.0.1}" \
    --port "${PORT:-9901}" \
    --log-level info
