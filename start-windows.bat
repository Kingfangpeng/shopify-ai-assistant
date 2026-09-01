REM Shopify AI Assistant - Windows Startup Script
@echo off
chcp 65001 >nul
title Shopify AI Assistant

echo ================================
echo   Shopify AI Assistant
echo ================================

if not exist .env (
    echo Please copy .env.example to .env and fill in your API keys
    pause
    exit /b 1
)

where conda >nul 2>&1
if errorlevel 1 (
    echo Please install Anaconda/Miniconda and make sure conda is in PATH
    pause
    exit /b 1
)

echo Activating Conda environment: RAG
call conda activate RAG
if errorlevel 1 (
    echo Failed to activate Conda environment RAG
    pause
    exit /b 1
)

if not exist logs mkdir logs

echo Starting Shopify MCP Server on port 8003...
start "Shopify MCP" /min cmd /c "call conda activate RAG && python mcp_servers/shopify_server.py"

echo Starting Ads MCP Server on port 8004...
start "Ads MCP" /min cmd /c "call conda activate RAG && python mcp_servers/ads_server.py"

timeout /t 3 /nobreak >nul

echo.
echo Main app: http://localhost:9901
echo API docs: http://localhost:9901/docs
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 9901 --reload

pause
