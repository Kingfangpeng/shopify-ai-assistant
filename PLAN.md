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

### 2026-09-04：聊天页接入深度分析循环（king 已确认）

目录与边界沿用既有架构：

```text
app/api/ops.py                         鉴权、请求校验、SSE 映射
app/services/chat/ops_service.py       绑定会话、过程与报告持久化、取消收尾
app/services/ops_agent_service.py      运行 LangGraph、输出计划/步骤/重规划事件
app/agent/ops/                         原有 Planner / Executor / Replanner
app/db/models.py + alembic/versions/   聊天消息增加有界过程元数据，兼容旧历史
frontend/src/api/client.js             通用 SSE 解码与普通/深度接口适配
frontend/src/pages/Chat.jsx            显式模式切换，传递当前所选模型
frontend/src/components/chat/          可折叠分析过程，包含计划、执行、重规划
```

- 划分一：显式“普通问答 / 深度分析”，不自动把所有问题升级成多次模型调用；仍在原聊天页，不新增运营页面。
- 划分二：报告与有界过程元数据保存在已有聊天消息中，通过增量迁移加列，不新增长期任务队列；刷新可回看，停止或断线取消，不后台续跑。
- 划分三：LangGraph 只处理执行状态，聊天服务持有用户归属和数据库事务；节点使用请求已验证的模型。保留旧执行器规则优先路径，本轮不改成完整动态参数 Agent。
- 验收：循环至少执行两步并输出重规划事件；模型贯穿全部节点；鉴权、CSRF、会话归属；最终报告只保存一次；取消/失败可回看；切换会话无串流；前端单测、后端测试、构建、桌面/手机截图与隔离 E2E。
- 不修改 `.env` 默认模型，不开放写工具，不提交或推送已有未提交代码。

### 2026-09-04：语义优先与 Flash 评估（king 已确认方向）

- 目录沿用既有边界：`app/agent/semantic_planner.py` 负责结构化意图规划；`app/services/chat/agent_service.py` 负责聊天编排；`app/agent/dispatcher.py` 只负责受限只读执行。
- 聊天入口不再由正则裁决知识库/Shopify，也不合并正则猜测与模型决定。模型输出知识库、实时数据、混合、普通问答、澄清或能力不足路由。
- 取舍一：接受一次额外模型推理，换取否定、指代和多意图理解；保留旧规则作为历史运营适配层，不作为聊天静默回退。
- 取舍二：结构化计划通过严格类型、工具允许列表和数量上限校验；规划失败返回可诊断错误，不让未验证的计划执行。
- 取舍三：本轮优化意图理解及混合知识上下文，不开放任意 GraphQL、不改变 Shopify 业务查询能力；日期与执行参数仍由现有服务端代码生成。完整的动态参数和多轮工具循环另行设计。
- 评估使用已验证可用的 `deepseek-v4-flash`，不修改本机默认模型。旧 48 题只做回归；新问题及预期路由在测评前固定，独立报告，不能依据新题改规则后仍称为盲测。
- 模型服务失败、无工具计划、非法工具、混合知识库离线、HTTP/SSE 一致性均增加自动化测试。测评不执行 Shopify 工具，不访问业务订单数据。

- 未登录访问业务 API 返回 401；不合法 CSRF、Origin 或 Host 被拒绝。
- 不存在任意目录索引入口；上传或索引失败时旧知识与旧文件保持可用。
- Embedding 维度变化不会自动删除 Milvus Collection。
- Shopify 八项工具具备 GraphQL 分页、节流、权限和错误测试，默认不冒充真实数据。
- 聊天上下文由 SQLite 恢复并参与多轮 RAG；旧 localStorage 数据只能在成功导入后清理。
- Python、前端单测、构建、端到端测试、依赖审计和密钥扫描通过后，才允许合并并推送私有 `main`。
