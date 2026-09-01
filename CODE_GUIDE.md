# Shopify AI Assistant 代码阅读指南

最后更新：2026-06-05 14:59:55 +08:00

> 更新规范：以后每次修改 `CODE_GUIDE.md` 或 `DEPLOYMENT.md`，必须同步更新文件顶部的“最后更新”日期时间，格式使用 `YYYY-MM-DD HH:mm:ss +08:00`。

## 项目定位

这是一个面向 Shopify 独立站运营的 AI 助手。它包含两条主线：

1. 知识库问答：上传 `.md` / `.txt` 文档后切分、向量化、写入 Milvus，聊天时从知识库召回内容，再交给大模型回答。
2. 运营分析 Agent：基于 LangGraph 的 `Planner -> Executor -> Replanner` 流程，调用 Shopify、广告、知识库、时间等工具，流式输出分析计划、步骤结果和最终报告。

前端是 React + Vite + Tailwind，后端是 FastAPI + LangChain + LangGraph + Milvus + Ollama Embedding。

## 目录地图

```text
app/
  main.py                         FastAPI 入口，注册路由并挂载前端静态文件
  config.py                       读取 .env 配置
  api/
    health.py                     健康检查 /health
    config.py                     非敏感配置 /api/config
    chat.py                       知识库问答 /api/chat、/api/chat_stream
    file.py                       上传、重建索引、分片统计和删除
    ops.py                        运营分析 Agent SSE 接口 /api/ops
    snapshot.py                   数据快照接口
  services/
    rag_agent_service.py          RAG 问答服务
    document_splitter_service.py  文档切分
    vector_embedding_service.py   Ollama embedding 封装
    vector_store_manager.py       Milvus VectorStore 封装
    vector_index_service.py       文件索引入口
    ops_agent_service.py          LangGraph Agent 服务
  agent/
    mcp_client.py                 MCP 工具客户端
    ops/
      planner.py                  生成分析计划
      executor.py                 执行单个步骤并调用工具
      replanner.py                决定继续、重规划或生成报告
      state.py                    Agent 状态结构
      utils.py                    工具描述格式化
  tools/
    knowledge_tool.py             知识库检索工具
    time_tool.py                  当前时间工具
    shopify_tool.py               Shopify 数据工具，未配置时走 mock
    ads_tool.py                   Facebook / Google Ads mock 工具

mcp_servers/
  shopify_server.py               Shopify MCP Server，默认 8003
  ads_server.py                   Ads MCP Server，默认 8004

frontend/
  src/
    App.jsx                       路由、会话持久化、全局布局
    api/client.js                 前端 API 封装
    components/Sidebar.jsx        侧边栏、会话列表
    components/StatusBadge.jsx    状态徽标
    pages/Chat.jsx                RAG 聊天页
    pages/Knowledge.jsx           知识库上传、分片查看、删除
    pages/History.jsx             本地会话历史
    pages/Settings.jsx            配置和健康状态

prompts/
  planner_system.md               Planner 提示词参考
  executor_system.md              Executor 提示词参考
  replanner_system.md             Replanner 提示词参考

static/                           Vite build 输出目录，FastAPI 直接托管
uploads/                          知识库上传文件目录
vector-database.yml               Milvus / etcd / MinIO / Attu Docker Compose
start-windows.bat                 Windows 启动脚本，默认激活 Conda RAG 环境
start.sh                          Linux/macOS 启动脚本，默认激活 Conda RAG 环境
```

## 启动链路

`app/main.py` 是后端入口。应用启动时会：

1. 加载 `.env` 到 `app.config.config`。
2. 初始化 Milvus 连接。
3. 注册后端 API。
4. 挂载 `static/assets`。
5. 将 `/`、`/chat`、`/knowledge`、`/history`、`/settings` 等前端路由回退到 `static/index.html`。

当前默认应用端口是 `9901`。

```text
浏览器
  -> http://localhost:9901/
  -> FastAPI 静态文件
  -> React Router 页面

API
  -> http://localhost:9901/health
  -> http://localhost:9901/api/*
```

## 配置读取

配置定义在 `app/config.py`，通过 `pydantic-settings` 从 `.env` 读取。

关键配置：

```text
HOST=0.0.0.0
PORT=9901
LLM_API_BASE=...
LLM_API_KEY=...
LLM_MODEL=...
RAG_MODEL=...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text:latest
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=shopify_kb
```

注意：`app/api/config.py` 只返回非敏感配置，不返回 API Key。Shopify 配置会排除 `your-store.myshopify.com`、`shpat_your_token_here` 这类模板占位值，避免误判为真实配置。

## 知识库问答链路

入口文件：`app/api/chat.py`

接口：

```text
POST /api/chat
POST /api/chat_stream
POST /api/chat/clear
GET  /api/chat/session/{session_id}
```

普通问答流程：

```text
用户问题
  -> app/api/chat.py
  -> rag_agent_service.query()
  -> vector_store_manager.similarity_search()
  -> Ollama 将问题转 embedding
  -> Milvus 召回 Top K 文档
  -> knowledge_tool.format_docs()
  -> 拼接 SystemMessage + HumanMessage
  -> LLM 返回答案
```

流式问答流程：

```text
POST /api/chat_stream
  -> yield status: 正在检索知识库
  -> yield status: 正在生成回答
  -> yield content chunks
  -> yield done
```

前端 `frontend/src/api/client.js` 会解析 SSE 的 `status`、`content`、`done`、`error`，`Chat.jsx` 展示状态提示并把会话持久化到 `localStorage`。

## 文档上传和分片索引

入口文件：`app/api/file.py`

接口：

```text
POST   /api/upload
POST   /api/index_directory
GET    /api/knowledge/stats
GET    /api/knowledge/chunks
DELETE /api/knowledge/file
```

兼容旧路径：

```text
GET /api/chunks
GET /api/knowledge_stats
```

上传流程：

```text
上传 .md / .txt
  -> 保存到 uploads/
  -> vector_index_service.index_single_file()
  -> document_splitter_service.split_document()
  -> vector_embedding_service.embed_documents()
  -> vector_store_manager.add_documents()
  -> 写入 Milvus collection: shopify_kb
```

`document_splitter_service.py` 对 Markdown 会先按 `#`、`##` 标题切分，再用 `RecursiveCharacterTextSplitter` 二次切分，并合并过小片段。

`vector_store_manager.py` 是 Milvus 操作中心，负责：

```text
add_documents()
delete_by_source()
delete_by_file()
similarity_search()
list_chunks()
get_stats()
```

## 运营 Agent 链路

入口文件：`app/api/ops.py`

接口：

```text
POST /api/ops
```

返回 SSE 事件：

```text
status
plan
step_complete
report
complete
error
```

核心服务：`app/services/ops_agent_service.py`

图结构：

```text
planner -> executor -> replanner
                    ^       |
                    |       |
                    +-------+

replanner 选择 respond 时结束
```

状态结构在 `app/agent/ops/state.py`：

```python
class PlanExecuteState(TypedDict):
    input: str
    plan: List[str]
    past_steps: List[tuple]
    response: str
    context: dict
    replan_count: int
```

### Planner

文件：`app/agent/ops/planner.py`

职责：

1. 查询知识库，获取相关运营经验。
2. 拉取本地工具和 MCP 工具描述。
3. 让 LLM 生成 3 到 6 步分析计划。
4. 如果失败，返回保底计划。

### Executor

文件：`app/agent/ops/executor.py`

职责：

1. 取 `plan[0]` 作为当前任务。
2. 绑定知识库、时间、MCP 工具。
3. 让 LLM 决定是否调用工具。
4. 执行工具调用。
5. 返回执行结果并移除当前步骤。

### Replanner

文件：`app/agent/ops/replanner.py`

职责：

1. 根据已执行步骤决定 `continue`、`replan` 或 `respond`。
2. 限制最大执行步数和重规划次数。
3. 信息足够时生成最终 Markdown 报告。

## 工具系统

### 本地工具

文件在 `app/tools/`。

```text
retrieve_knowledge     检索知识库
get_current_time       获取当前时间
get_orders_summary     订单汇总
get_abandoned_checkouts 弃购数据
get_inventory_levels   库存
get_product_performance 产品表现
get_customer_segments  客户分层
get_refund_stats       退款
get_discount_performance 优惠码
get_order_list         订单列表
get_facebook_*         Facebook mock 数据
get_google_*           Google mock 数据
```

Shopify 未配置真实域名和 token 时，`shopify_tool.py` 会返回 mock 数据。模板占位值不会被视为有效配置。

### MCP 工具

文件在 `mcp_servers/`。

MCP Server 只是把本地工具包装成独立 HTTP 工具服务：

```text
Shopify MCP: http://localhost:8003/mcp
Ads MCP:     http://localhost:8004/mcp
```

Agent 通过 `app/agent/mcp_client.py` 拉取 MCP 工具。

## 前端结构

前端入口是 `frontend/src/main.jsx` 和 `frontend/src/App.jsx`。

页面：

```text
/chat       知识库聊天
/knowledge  知识库文件、分片、上传、删除
/history    本地会话历史
/settings   健康状态和非敏感配置
```

会话数据保存在浏览器 `localStorage`：

```text
shopify_ai_sessions
shopify_ai_active_session
shopify_ai_files
```

前端构建输出到 `static/`：

```bash
cd frontend
npm.cmd run build
```

构建后 FastAPI 会直接托管 `static/index.html` 和 `static/assets/*`。

## 关键接口速查

```text
GET  /health
GET  /api/config

POST /api/chat
POST /api/chat_stream
POST /api/chat/clear
GET  /api/chat/session/{session_id}

POST /api/upload
POST /api/index_directory
GET  /api/knowledge/stats
GET  /api/knowledge/chunks?filename=ABOk_Ark2000.md&limit=50&offset=0
DELETE /api/knowledge/file?file_path=ABOk_Ark2000.md

POST /api/ops
```

## 推荐阅读顺序

第一次看项目，按这个顺序读：

1. `app/main.py`
2. `app/config.py`
3. `app/api/chat.py`
4. `app/services/rag_agent_service.py`
5. `app/services/vector_store_manager.py`
6. `app/api/file.py`
7. `app/services/vector_index_service.py`
8. `app/services/document_splitter_service.py`
9. `app/api/ops.py`
10. `app/services/ops_agent_service.py`
11. `app/agent/ops/planner.py`
12. `app/agent/ops/executor.py`
13. `app/agent/ops/replanner.py`
14. `frontend/src/App.jsx`
15. `frontend/src/api/client.js`
16. `frontend/src/pages/Chat.jsx`
17. `frontend/src/pages/Knowledge.jsx`

## 验证命令

使用 Conda `RAG` 环境：

```bash
conda activate RAG
python -m compileall app mcp_servers
```

前端：

```bash
cd frontend
npm.cmd run build
```

健康检查：

```bash
curl http://localhost:9901/health
```

知识库统计：

```bash
curl http://localhost:9901/api/knowledge/stats
```

知识库问答：

```bash
curl -X POST "http://localhost:9901/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"Id\":\"test-1\",\"Question\":\"这款 Portable Power Station 的容量是多少？\"}"
```

## 常见问题

### 1. 后端启动时 Milvus 报错

项目导入 `vector_store_manager` 时会初始化 Milvus 连接。Milvus 没启动时，后端可能连 `/health` 都起不来。

先确认：

```bash
docker ps -a --filter name=milvus
```

再确认端口：

```bash
Test-NetConnection -ComputerName localhost -Port 19530
```

### 2. Ollama Embedding 失败

确认 Ollama 正常：

```bash
curl http://localhost:11434/api/tags
ollama list
```

需要有：

```text
nomic-embed-text:latest
```

### 3. Shopify 显示未配置

这是正常行为。只有真实域名和真实 token 才会显示已配置；模板值 `your-store.myshopify.com` 和 `shpat_your_token_here` 会被忽略。

### 4. 前端改了但后端页面没变

需要重新构建：

```bash
cd frontend
npm.cmd run build
```

FastAPI 托管的是 `static/`，不是 `frontend/src/`。

### 5. PowerShell 中文显示乱码

接口本身返回 UTF-8，PowerShell 输出可能显示乱码。浏览器页面一般正常。必要时执行：

```powershell
chcp 65001
```
