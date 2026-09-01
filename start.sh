#!/usr/bin/env bash
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BOLD}Shopify AI Assistant${NC}"
echo "─────────────────────────────────────"

if [ ! -f .env ]; then
    echo -e "${YELLOW}未找到 .env，请先复制模板: cp .env.example .env${NC}"
    exit 1
fi

if [ "${CONDA_DEFAULT_ENV:-}" != "RAG" ]; then
    if command -v conda &>/dev/null; then
        echo -e "${GREEN}激活 Conda 环境 RAG...${NC}"
        eval "$(conda shell.bash hook)"
        conda activate RAG
    else
        echo -e "${YELLOW}未检测到 conda，请确认已在包含项目依赖的 Python 环境中运行${NC}"
    fi
fi

mkdir -p logs

cleanup() {
    echo -e "\n${YELLOW}正在关闭服务...${NC}"
    [ -n "${SHOPIFY_PID:-}" ] && kill "$SHOPIFY_PID" 2>/dev/null || true
    [ -n "${ADS_PID:-}" ] && kill "$ADS_PID" 2>/dev/null || true
    echo -e "${GREEN}已停止${NC}"
}
trap cleanup INT TERM EXIT

echo -e "${GREEN}启动 Shopify MCP Server (port 8003)...${NC}"
python mcp_servers/shopify_server.py > logs/shopify_mcp.log 2>&1 &
SHOPIFY_PID=$!

echo -e "${GREEN}启动 Ads MCP Server (port 8004)...${NC}"
python mcp_servers/ads_server.py > logs/ads_mcp.log 2>&1 &
ADS_PID=$!

sleep 2

if ! kill -0 "$SHOPIFY_PID" 2>/dev/null; then
    echo -e "${RED}Shopify MCP Server 启动失败，查看 logs/shopify_mcp.log${NC}"
    exit 1
fi
if ! kill -0 "$ADS_PID" 2>/dev/null; then
    echo -e "${RED}Ads MCP Server 启动失败，查看 logs/ads_mcp.log${NC}"
    exit 1
fi

echo -e "${GREEN}MCP Servers 就绪${NC}"
echo -e "${GREEN}启动主应用 http://localhost:9901${NC}"
echo "─────────────────────────────────────"

python -m uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-9901}" \
    --reload \
    --log-level info
