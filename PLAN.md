# Shopify AI Assistant 安全升级实施计划

## 目标

本轮将项目从单机演示型 MVP 升级为默认仅本机访问、具备管理员登录、服务端会话、可靠知识库生命周期和真实 Shopify GraphQL 数据能力的本地运营助手。Facebook 与 Google Ads 暂不实现，默认不启动相关服务或工具。

## 已确认目录结构

```text
app/
  auth/                     管理员认证、密码哈希、会话、CSRF、限流
  db/                       SQLite 连接、模型、迁移和仓储
  integrations/shopify/     GraphQL 客户端、查询、数据模型、聚合服务
  services/
    knowledge/              文件生命周期、切片、向量、回收站
    chat/                   会话历史、RAG 上下文和消息持久化
  api/                      HTTP/SSE、鉴权和响应映射
  tools/                    只读 Agent 工具适配
  agent/                    Planner/Executor/Replanner
  cli.py                    管理员和知识库维护命令

frontend/src/
  auth/                     登录状态、路由保护、CSRF
  components/ui/            通用界面组件
  pages/                    登录及现有业务页面
  api/                      统一请求和 SSE 客户端

tests/
  backend/                  后端单元与集成测试
  frontend/                 前端组件测试
  e2e/                      浏览器端到端测试
```

## 核心边界与耦合关系

1. Shopify GraphQL 客户端只负责远端协议、分页、节流和错误转换；聚合服务负责订单、库存等业务指标；LangChain 工具只负责适配，避免 Agent 与 Shopify 协议耦合。
2. SQLite 保存用户、认证会话、聊天和知识文档元数据；Milvus 只保存带 `document_id` 的向量；文件系统只保存源文件与七天回收站。
3. 知识库服务独占上传、索引、替换、删除和恢复流程。API 不接受服务器目录或绝对路径，任何失败都不得删除上一版可用数据。

## 已确认实现决策

- Shopify Admin API 固定使用 GraphQL `2026-07`，八项现有 Shopify 工具全部迁移为真实只读查询。
- 未配置 Shopify 时默认返回未连接；只有 `SHOPIFY_DEMO_MODE=true` 才允许带明显标识的演示数据。
- Agent 进程内调用 Shopify 工具；MCP 代码保留为可选适配层，启动脚本默认不启动 MCP。
- 使用单管理员模型。管理员通过交互式 CLI 创建，密码以 Argon2id 哈希保存。
- 使用 SQLite 保存不透明服务端会话、聊天记录、文档状态和审计事件；浏览器不持久化认证令牌。
- 知识文档删除后进入七天回收站；Milvus 默认仅绑定本机，不启用自身用户鉴权。
- 前端采用石墨灰、暖白和 Shopify 绿的商家运营台风格，只精修登录及现有四个页面。
- 默认监听 `127.0.0.1`；生产模式关闭详细异常与 API 文档，所有业务 API 必须登录。

## 验收门槛

- 未登录访问业务 API 返回 401；不合法 CSRF、Origin 或 Host 被拒绝。
- 不存在任意目录索引入口；上传或索引失败时旧知识与旧文件保持可用。
- Embedding 维度变化不会自动删除 Milvus Collection。
- Shopify 八项工具具备 GraphQL 分页、节流、权限和错误测试，默认不冒充真实数据。
- 聊天上下文由 SQLite 恢复并参与多轮 RAG；旧 localStorage 数据只能在成功导入后清理。
- Python、前端单测、构建、端到端测试、依赖审计和密钥扫描通过后，才允许合并并推送私有 `main`。
