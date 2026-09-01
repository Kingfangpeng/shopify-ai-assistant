# Shopify AI Assistant 部署与运行指南

最后更新：2026-06-05 14:59:55 +08:00

> 更新规范：以后每次修改 `CODE_GUIDE.md` 或 `DEPLOYMENT.md`，必须同步更新文件顶部的“最后更新”日期时间，格式使用 `YYYY-MM-DD HH:mm:ss +08:00`。

## 当前项目运行方式

本项目当前按以下方式运行：

```text
Python 环境：Conda 环境 RAG
后端框架：FastAPI
后端端口：9901
MCP Shopify：8003
MCP Ads：8004
向量数据库：Docker 中的 Milvus，端口 19530
Milvus 管理界面：Attu，端口 8000
Embedding：本地 Ollama，端口 11434，模型 nomic-embed-text:latest
前端：React + Vite，构建产物在 static/
```

访问地址：

```text
应用首页：http://localhost:9901/
API 文档：http://localhost:9901/docs
健康检查：http://localhost:9901/health
Attu 管理界面：http://localhost:8000
```

注意：`8000` 是 Attu 管理界面端口，不是应用 API 端口。

## 前置依赖

### 1. Conda 环境

项目默认使用 Conda 环境 `RAG`。

```bash
conda activate RAG
python --version
```

推荐 Python 版本：

```text
Python 3.11 / 3.12
```

项目约束是：

```text
>=3.11,<3.14
```

### 2. Python 依赖

依赖定义在 `pyproject.toml`。

快速确认依赖：

```bash
conda activate RAG
python -c "import fastapi, langchain, pymilvus; print('deps ok')"
```

核心依赖包括：

```text
fastapi
uvicorn
sse-starlette
langchain
langchain-openai
langchain-milvus
langchain-text-splitters
langgraph
langchain-mcp-adapters
fastmcp
pymilvus
pydantic-settings
python-dotenv
loguru
httpx
aiohttp
ShopifyAPI
```

### 3. Node.js 依赖

前端依赖在 `frontend/package.json`。

首次安装：

```bash
cd frontend
npm install
```

构建：

```bash
cd frontend
npm.cmd run build
```

### 4. Docker Desktop

Milvus 运行在 Docker 中。

确认 Docker 可用：

```bash
docker --version
docker compose version
```

### 5. Ollama

Ollama 用于本地 embedding。

确认服务：

```bash
curl http://localhost:11434/api/tags
```

需要拉取模型：

```bash
ollama pull nomic-embed-text
ollama list
```

## 环境变量

复制模板：

```bash
copy .env.example .env
```

Linux/macOS：

```bash
cp .env.example .env
```

核心配置：

```env
APP_NAME=Shopify AI Assistant
APP_VERSION=1.0.0
DEBUG=false
HOST=0.0.0.0
PORT=9901

LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=sk-your-key
LLM_MODEL=deepseek-chat
RAG_MODEL=deepseek-chat

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text:latest
EMBEDDING_DIMENSIONS=768

MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_TIMEOUT=10000
MILVUS_COLLECTION=shopify_kb

RAG_TOP_K=3
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100

MCP_SHOPIFY_URL=http://localhost:8003/mcp
MCP_ADS_URL=http://localhost:8004/mcp
```

Shopify 可以先不配置。未配置或使用模板占位值时，系统会使用 mock 数据。

真实 Shopify 配置：

```env
SHOPIFY_STORE_DOMAIN=your-real-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxx
```

模板值不会被视为真实配置：

```text
your-store.myshopify.com
shpat_your_token_here
```

## 启动 Milvus

如果 Milvus 已经运行，可以跳过。

启动：

```bash
docker compose -f vector-database.yml up -d
```

检查：

```bash
docker ps -a --filter name=milvus
```

期望看到：

```text
milvus-standalone   Up ... (healthy)   0.0.0.0:19530->19530/tcp
milvus-etcd         Up ... (healthy)
milvus-minio        Up ... (healthy)
milvus-attu         Up ...             0.0.0.0:8000->3000/tcp
```

检查端口：

```powershell
Test-NetConnection -ComputerName localhost -Port 19530
```

检查健康接口：

```bash
curl http://localhost:9091/healthz
```

## 启动应用

### Windows

当前推荐方式：

```bat
start-windows.bat
```

脚本会：

1. 检查 `.env`。
2. 激活 Conda 环境 `RAG`。
3. 启动 Shopify MCP Server，端口 `8003`。
4. 启动 Ads MCP Server，端口 `8004`。
5. 启动 FastAPI 主应用，端口 `9901`。

也可以手动启动：

```bash
conda activate RAG
python mcp_servers/shopify_server.py
python mcp_servers/ads_server.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 9901 --reload
```

手动启动时建议分别开 3 个终端。

### Linux/macOS

```bash
chmod +x start.sh
./start.sh
```

脚本会优先激活 Conda 环境 `RAG`。如果没有 Conda，请先手动进入包含项目依赖的 Python 环境。

## 构建前端

前端开发目录：

```text
frontend/
```

构建命令：

```bash
cd frontend
npm.cmd run build
```

Linux/macOS：

```bash
cd frontend
npm run build
```

构建输出：

```text
static/index.html
static/assets/*
```

FastAPI 会托管 `static/`。所以修改前端后，必须重新 build 才能在 `http://localhost:9901/` 看到更新。

## 开发模式

如需前端热更新：

```bash
cd frontend
npm.cmd run dev
```

Vite 默认地址：

```text
http://localhost:5173
```

`frontend/vite.config.js` 已配置代理：

```text
/api    -> http://localhost:9901
/health -> http://localhost:9901
```

开发模式下仍需要后端服务已运行。

## 验证项目是否跑通

### 1. 后端健康检查

```bash
curl http://localhost:9901/health
```

期望：

```json
{
  "code": 200,
  "data": {
    "status": "healthy",
    "milvus": {
      "status": "connected"
    }
  }
}
```

### 2. 配置检查

```bash
curl http://localhost:9901/api/config
```

期望看到：

```json
{
  "app_name": "Shopify AI Assistant",
  "app_version": "1.0.0",
  "milvus_collection": "shopify_kb",
  "shopify_configured": false
}
```

如果使用真实 Shopify 配置，`shopify_configured` 才应为 `true`。

### 3. 知识库统计

```bash
curl http://localhost:9901/api/knowledge/stats
```

期望：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total_chunks": 1,
    "files": [
      {
        "file_name": "ABOk_Ark2000.md",
        "chunk_count": 1
      }
    ]
  }
}
```

数量以你当前 Milvus 数据为准。

### 4. 知识库分片

```bash
curl "http://localhost:9901/api/knowledge/chunks?limit=5"
```

期望返回：

```json
{
  "code": 200,
  "data": {
    "chunks": [],
    "limit": 5,
    "offset": 0,
    "has_more": false
  }
}
```

有已索引文档时，`chunks` 会包含 `file_name`、`source`、`content_preview`、`char_count` 等字段。

### 5. 知识库问答

PowerShell：

```powershell
$body = @{
  Id = "test-1"
  Question = "这款 Portable Power Station 的容量是多少？"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:9901/api/chat `
  -ContentType "application/json" `
  -Body $body
```

期望：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "success": true,
    "answer": "...",
    "errorMessage": null
  }
}
```

### 6. 运营 Agent

```bash
curl -X POST "http://localhost:9901/api/ops" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"最近7天ROAS为什么下跌？\"}" \
  --no-buffer
```

期望看到 SSE 流式事件：

```text
status
plan
step_complete
report
complete
```

该接口会调用 LLM 和 MCP 工具，耗时比普通问答更长。

## 上传知识库文档

接口：

```text
POST /api/upload
```

curl：

```bash
curl -X POST "http://localhost:9901/api/upload" \
  -F "file=@uploads/ABOk_Ark2000.md"
```

上传成功后会自动：

1. 保存文件到 `uploads/`。
2. 切分文档。
3. 调用 Ollama 生成 embedding。
4. 写入 Milvus。

重建全部索引：

```bash
curl -X POST "http://localhost:9901/api/index_directory"
```

删除某个文件的知识库分片：

```bash
curl -X DELETE "http://localhost:9901/api/knowledge/file?file_path=ABOk_Ark2000.md"
```

## 前端页面

```text
/chat       RAG 问答
/knowledge  知识库上传、统计、分片查看、删除
/history    本地会话历史
/settings   健康状态、配置状态
```

会话历史保存在浏览器 `localStorage`。后端也有简单内存会话记录，但刷新和跨会话恢复主要靠前端本地持久化。

## 生产部署建议

生产环境建议：

```text
操作系统：Ubuntu 22.04
CPU：至少 2 核，推荐 4 核
内存：至少 4GB，推荐 8GB
硬盘：至少 40GB，推荐 80GB SSD
```

生产环境需要：

1. Docker 运行 Milvus。
2. Ollama 运行 embedding 模型。
3. Python 环境安装项目依赖。
4. 前端先 `npm run build`。
5. 使用 systemd 或进程管理器运行：
   - `mcp_servers/shopify_server.py`
   - `mcp_servers/ads_server.py`
   - `python -m uvicorn app.main:app --host 0.0.0.0 --port 9901 --workers 2`

示例 systemd 主应用命令：

```ini
ExecStart=/path/to/python -m uvicorn app.main:app --host 0.0.0.0 --port 9901 --workers 2
```

如果服务器使用 `uv` 管理依赖，也可以继续使用：

```ini
ExecStart=/root/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 9901 --workers 2
```

本地 Windows 开发以 Conda `RAG` 环境为准。

## 常见故障

### 1. `/health` 不是 healthy

检查 Milvus：

```bash
docker ps -a --filter name=milvus
curl http://localhost:9091/healthz
```

检查端口：

```powershell
Test-NetConnection -ComputerName localhost -Port 19530
```

### 2. 后端启动时直接失败

常见原因：

```text
Milvus 未启动
Conda RAG 环境未激活
缺少 Python 依赖
.env 不存在
LLM_API_KEY 未配置
```

检查：

```bash
conda activate RAG
python -c "import app.main; print('import ok')"
```

### 3. 上传文档失败

检查：

```text
文件必须是 .md 或 .txt
文件大小不能超过 10MB
Ollama 必须运行
Milvus 必须 connected
```

### 4. RAG 问答失败

检查：

```text
LLM_API_BASE 是否正确
LLM_API_KEY 是否有效
RAG_MODEL 是否被服务商支持
Ollama 是否有 nomic-embed-text:latest
Milvus collection 是否存在
```

### 5. 前端页面没有更新

重新构建：

```bash
cd frontend
npm.cmd run build
```

然后刷新：

```text
http://localhost:9901/
```

### 6. Docker Compose 提示容器名冲突

如果已有 `milvus-etcd`、`milvus-minio`、`milvus-standalone` 正在运行且 healthy，可以直接复用，不必删除。

查看：

```bash
docker ps -a --filter name=milvus
```

### 7. PowerShell 中文乱码

接口返回是 UTF-8，PowerShell 可能显示乱码。

可先执行：

```powershell
chcp 65001
```

浏览器和前端页面通常显示正常。

## 维护检查清单

每次修改代码后，建议至少跑：

```bash
conda activate RAG
python -m compileall app mcp_servers
```

```bash
cd frontend
npm.cmd run build
```

```bash
curl http://localhost:9901/health
curl http://localhost:9901/api/knowledge/stats
```

每次修改 `CODE_GUIDE.md` 或 `DEPLOYMENT.md`，必须更新两个文件顶部的“最后更新”时间。
