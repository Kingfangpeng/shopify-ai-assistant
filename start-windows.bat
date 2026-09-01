@echo off
chcp 65001 >nul
title Shopify AI Assistant

if not exist .env (
    echo 请先复制 .env.example 为 .env 并填写本地配置
    pause
    exit /b 1
)
if not exist .venv\Scripts\python.exe (
    echo 未找到项目虚拟环境，请先运行 py -m uv sync --group dev
    pause
    exit /b 1
)
if not exist logs mkdir logs

echo 主应用：http://127.0.0.1:9901
echo 默认不启动 Shopify/Ads MCP；Agent 使用进程内只读 Shopify 工具。
.venv\Scripts\alembic.exe upgrade head
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9901
pause
