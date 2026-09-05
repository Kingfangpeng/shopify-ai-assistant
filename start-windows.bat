@echo off
setlocal
title Shopify AI Assistant
set "APP_URL=http://127.0.0.1:9901"
set "DOCKER_DESKTOP_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"

if not exist .env (
    echo [ERROR] Missing .env. Copy .env.example to .env and configure it first.
    pause
    exit /b 1
)
if not exist .venv\Scripts\python.exe (
    echo [ERROR] Missing .venv. Run: py -m uv sync --group dev
    pause
    exit /b 1
)
if not exist logs mkdir logs

set "VECTOR_CONFIGURED=1"
findstr /r /b /c:"MINIO_ROOT_USER=." .env | findstr /v /c:"replace-with" >nul
if errorlevel 1 set "VECTOR_CONFIGURED=0"
findstr /r /b /c:"MINIO_ROOT_PASSWORD=." .env | findstr /v /c:"replace-with" >nul
if errorlevel 1 set "VECTOR_CONFIGURED=0"

docker info >nul 2>&1
if errorlevel 1 if exist "%DOCKER_DESKTOP_EXE%" (
    echo Docker Desktop is not running. Starting it in the background...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%DOCKER_DESKTOP_EXE%' -WindowStyle Hidden"
    echo Waiting up to 90 seconds for Docker Engine...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(90); do { docker info *> $null; if ($LASTEXITCODE -eq 0) { exit 0 }; Start-Sleep -Seconds 2 } while ((Get-Date) -lt $deadline); exit 1"
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [WARN] Docker Desktop is not running. Knowledge chat is unavailable.
    echo        General chat will continue in model-only mode; knowledge documents are unavailable.
) else if "%VECTOR_CONFIGURED%"=="0" (
    echo [WARN] MINIO_ROOT_USER or MINIO_ROOT_PASSWORD is missing in .env.
    echo        Add random local credentials, then run this script again.
) else (
    echo Starting local Milvus and MinIO...
    docker compose -f vector-database.yml up -d --wait --wait-timeout 180
    if errorlevel 1 echo [WARN] Vector database startup failed. Check Docker logs.
)

echo App: %APP_URL%
echo Shopify and Ads MCP processes are disabled by default.
if /i "%STARTUP_CHECK_ONLY%"=="1" exit /b 0

.venv\Scripts\python.exe -c "import json,urllib.request; data=json.load(urllib.request.urlopen('%APP_URL%/health',timeout=2)); raise SystemExit(0 if data.get('status')=='ok' and data.get('service')=='Shopify AI Assistant' else 1)" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Shopify AI Assistant is already running at %APP_URL%.
    echo        Keep using the existing process; a second server is not needed.
    exit /b 0
)

.venv\Scripts\python.exe -c "import socket; sock=socket.socket(); sock.settimeout(1); result=sock.connect_ex(('127.0.0.1',9901)); sock.close(); raise SystemExit(0 if result==0 else 1)" >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] Port 9901 is occupied by another application.
    echo         Run: Get-NetTCPConnection -LocalPort 9901 -State Listen
    pause
    exit /b 1
)

.venv\Scripts\alembic.exe upgrade head
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9901
pause
endlocal
