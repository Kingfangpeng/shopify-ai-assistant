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

### 2026-09-09：RAG 路由修复、可观察过程与可追溯引用（king 已确认）

本轮以 `E:\cursor code\Claude\Shopify_ai` 为改造目标，`E:\Trae_code\chatbot` 只作为交互与实现对照，不直接复制其 Chroma 检索层。模型、Embedding 与验收继续只使用本地 Ollama，不调用 DeepSeek API。

#### 已复现问题与根因

- Ark3600 文档在 SQLite 中为 `active`，版本 1，共 19 个分片；同一句“Ark3600的参数是什么”直接检索时能够返回 5 条结果，产品规格分片位于前 2 名。
- 本地 `qwen3.5:27b` 的语义规划把该问题判为 `route=chat`，因此聊天编排没有调用知识库。强制 `route=knowledge` 后可以生成包含容量、输入、输出、尺寸、重量等参数及 chunk 引用的回答。
- 后端普通聊天的完成事件已经包含 `citations`，但前端只保存回答正文；SSE 持久化也没有保存引用和普通聊天过程。页面刷新后更无法回看检索过程。
- 深度分析的 Planner 在节点内部静默检索知识库，外层只能看到“制定计划完成”，无法告诉用户是否检索、命中哪些文件或是否降级。
- 对照项目 `E:\Trae_code\chatbot` 的优点是能显示检索文件、片段和距离；但它使用 Chroma 单路稠密 Top-K、固定字符切片，并在阈值过滤为空时重新采用全部结果。调试展示还会重复检索一次，展示证据与实际回答证据可能不一致。

#### 目标目录结构

```text
app/
  services/
    retrieval/
      models.py               统一检索结果、证据、引用与公开过程模型
      evidence_policy.py      型号归一化、相关性门槛、证据采用/拒绝规则
      pipeline.py             稠密/BM25、RRF、FlashRank 与证据选择编排
    vector_store_manager.py   保留为 Milvus 读写、索引与别名切换适配器
    rag_agent_service.py      兼容现有调用，组装受证据约束的回答上下文
    chat/
      events.py               普通/深度模式共用的版本化、安全事件协议
      agent_service.py        路由、知识探测、工具和生成的顶层编排
      service.py              回答、引用和有界过程的 SQLite 持久化
    ops_agent_service.py      深度分析节点与统一事件协议的桥接
  agent/ops/planner.py        只负责生成计划，不再私下检索知识库
  api/chat.py                 REST/SSE 使用同一结果模型和持久化字段

frontend/src/
  components/chat/
    AgentActivity.jsx         可折叠活动时间线，显示调用目的、状态和耗时
    CitationList.jsx          文件、版本、标题、chunk、片段和相关分数
  api/client.js               解码统一事件，不丢弃引用和过程
  pages/Chat.jsx              每条助手消息绑定过程与引用，刷新后可回看
  pages/Knowledge.jsx         通过 document_id/chunk_id 定位引用分片

tests/
  backend/
    test_rag_routing_and_trace.py
    test_rag_citations.py
  frontend/
    Chat.test.jsx
  fixtures/
    rag_product_identifier_routing.json 产品名/型号、实时数据、写操作与通用概念边界
```

#### 模块边界与数据流

1. `vector_store_manager.py` 只处理 Milvus、用户过滤、稠密/BM25 双路召回和影子集合；`retrieval/pipeline.py` 负责一次请求内的查询归一化、RRF、FlashRank、证据采用和公开统计。回答上下文、前端片段和引用必须来自同一个 `RetrievalResult`，禁止为了展示再次检索。
2. 语义规划仍负责 Shopify 工具与写操作边界。`knowledge`/`mixed` 路由直接检索；`chat` 路由执行一次本地只读知识探测，只有证据策略通过才升级为知识回答。型号采用大小写、连字符和全半角归一化，保留 SKU/数字；相关性阈值通过固定集校准，不凭单次 Ark3600 结果硬编码。普通寒暄或无相关证据仍走通用回答。
3. 普通与深度模式共用版本化事件：`model_call_started/completed`、`route_completed`、`retrieval_started/completed`、`rerank_completed`、`evidence_selected`、`tool_started/completed`、`generation_started/completed`、`citation_checked`。前端展示模型正在执行的外部动作、数据来源、结果摘要和耗时，不展示模型隐藏思维链、系统 Prompt 或完整原始工具输出。
4. 深度分析在进入 LangGraph Planner 前通过统一 Pipeline 取得知识证据并写入 state；Planner 不再自行调用 `retrieve_knowledge`。这样知识检索可流式显示，普通与深度模式引用口径一致。
5. 引用以 `document_id + version + chunk_id` 为身份，附安全截断的片段、标题、文件名、排序和分数。生成后只接受本轮证据集中的引用；引用与有界事件写入现有 `details_json`，刷新后可回看。前端链接到知识库页面对应文档和 chunk，不暴露服务器存储路径。

#### 关键取舍

1. **保留 Milvus 混合检索，吸收 chatbot 的可视化交互。** 当前项目已有稠密 20 + BM25 20、RRF 12、FlashRank 5、用户隔离、版本和影子别名，能力高于 chatbot 的 Chroma 单向量 Top-K。替换底座会丢失生产能力，收益只在界面层。
2. **展示可审计活动，不展示隐藏推理文本。** 用户能看到模型何时路由、检索、精排、调用工具、生成和校验引用，以及每步结果；内部思维链不稳定且可能包含系统信息，不作为产品数据。
3. **回答与展示共享同一次检索。** chatbot 为调试面板和回答各检索一次，可能出现两份结果。新结构将检索结果作为单一事实源，同时供 Prompt、SSE、引用卡片和历史记录使用。
4. **对 `chat` 路由增加本地证据探测，而非只修改 Prompt。** Prompt 升级为新版本并补充产品型号示例，但证据探测负责消除一次路由误判造成的完全漏检；证据门槛负责阻止无关片段污染普通回答。

#### 开源调研结论

- LangGraph 的流式协议把 `messages`、`updates`、`tools`、`lifecycle` 和 `custom` 分为不同事件通道，适合采用“版本化事件信封 + 类型化载荷”，而不是让前端解析日志字符串：<https://github.com/langchain-ai/streaming-cookbook>。
- Vercel AI SDK 将文档来源建模为独立的 `source-document` 消息部分，包含稳定 ID、标题、文件名和媒体类型；本项目沿用“正文与来源分开传输和渲染”的思路，不把文件名只拼进回答文本：<https://github.com/vercel/ai/blob/main/packages/ai/src/ui/ui-messages.ts>。
- OpenInference 将 Agent、LLM、Retriever、Reranker、Tool 设为独立 span 类型，并为检索文档定义 ID、分数和内容属性；本项目的公开事件字段采用相同职责划分，但暂不引入外部遥测服务：<https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md>。

#### 验收标准

- “Ark3600的参数是什么”无需出现“上传、文档、手册”等提示词，也会检索当前用户知识库，回答包含有效文件、版本和 chunk 引用；页面明确显示路由、检索、候选、精排、证据、生成和引用校验状态。
- 无相关资料的普通问题不会采用伪相关分片；知识库离线、FlashRank 降级和零命中分别显示不同状态，不再统一表现为“没资料”。
- 普通与深度模式都保存有界过程和引用；刷新会话后仍能回看，切换用户无法读取他人的文件名、片段、分数或 chunk。
- 后端覆盖产品型号路由回退、证据门槛、一次检索复用、引用白名单、SSE/REST 一致性和用户隔离；前端覆盖实时过程、引用卡片、历史恢复和失败状态。
- 使用合成型号固定集校准门槛，并以当前本机 Ark3600 文档做不提交仓库的真实端到端验证；运行后端测试、前端 Vitest、构建、RAG 固定集、相关路由回归和浏览器截图。
- 所有真实模型验证使用 `qwen3.5:27b`，Embedding 使用 `nomic-embed-text:latest`，不访问 `api.deepseek.com`。

### 2026-09-08：P1 六项生产化优化（king 已确认）

本轮在普通聊天和 LangGraph 深度分析之间复用同一套记忆、检索、工具协议和 Prompt 版本能力；模型相关开发与验收固定使用本地 Ollama qwen3.5:27b，测试禁止访问 DeepSeek API。

目录结构与模块边界：

- app/services/memory：会话摘要、长期记忆候选、确认、冲突、TTL 与上下文组装。
- app/services/retrieval：Milvus 稠密/BM25 双路召回、RRF、FlashRank 与引用。
- app/agent/tooling：统一 ToolSpec、严格参数模型、本地/MCP Provider。
- app/prompts：Prompt Registry、版本、锁文件和组合摘要。
- app/api/memory.py 与 frontend/src/pages/Memory.jsx：鉴权 API 与候选审核界面。
- tests/fixtures/quality：RAG、工具参数与记忆评估冻结数据。

核心边界与取舍：

1. SQLite 是会话摘要和长期记忆的事实源；只有 active 记忆进入上下文，模型自动提取的 candidate 必须由用户确认。凭据、密码、Token 与支付信息禁止保存，冲突通过新版本替代而非覆盖。
2. 知识生命周期仍由知识库服务独占；检索服务只读取带 user_id、document_id、version、chunk_id 的有效分片。Milvus 混合集合通过影子重建、数量核验和别名切换发布。
3. ToolSpec 是17个Shopify只读工具的唯一事实源；本地 Provider 与 MCP Provider 使用相同 Schema。MCP 默认关闭，启用后失败不静默回退。
4. Prompt 与工具目录、输出 Schema 共同生成版本摘要；修改 Prompt 未升级版本或未通过冻结回归时禁止交付。

验收标准：

- 500条RAG固定用例达到 Recall@5≥95%、MRR/NDCG@10≥90%、权限泄漏为0、预热P95≤1.5秒。
- 300条参数用例字段级准确率≥98%，非法参数执行次数为0。
- 记忆候选未经确认不生效；冲突、过期、敏感信息和用户隔离均有自动化测试。
- 普通与深度模式通过本地和MCP两种Provider的一致性测试；全部模型验证只使用本地Qwen。


### 2026-09-05：生产规模语义路由评估集（king 已确认）

目录与边界如下：

```text
tests/fixtures/evaluation/
  core_gold.json             300 条核心工具与路由用例
  paraphrase_noise.json      500 条口语、噪声与多语言变体
  multiturn_context.json     250 条多轮、改口、否定与指代用例
  mixed_rag_shopify.json     200 条知识库与实时数据混合用例
  safety_boundary.json       250 条越权、写操作、注入与未接入能力用例
  manifest.json              套件版本、数量、随机种子与文件摘要
scripts/
  generate_production_routing_cases.py  确定性生成并冻结数据集
  evaluate_tool_routing.py              加载套件并输出分层指标
tests/backend/
  test_production_routing_dataset.py     校验结构、分布、唯一性与可复现性
volumes/evaluations/                     Git 忽略的真实模型逐题报告
```

- 划分一：300 条核心集强调人工可读的业务语义，1200 条规模集通过受控模板组合生成；生成器只负责数据，不修改规划提示词或路由实现，避免评估集与被测逻辑耦合。
- 划分二：五个数据集按风险类型拆分，通过清单统一加载；清单固定版本、随机种子、条数和 SHA-256，防止评估后无记录地改题。
- 划分三：评估器只调用规划层，不执行 Shopify 工具或读取订单数据；本地完整运行真实模型，CI 只校验数据结构、标签分布和少量替身测试，避免持续产生模型费用。
- 验收：五个文件合计 1500 条，ID 与问题均唯一，17 个 Shopify 工具和六类路由都有覆盖；测试集可确定性重建；报告包含严格准确率、工具 Precision/Recall/F1、路由混淆矩阵、分类指标、重复稳定性和 P50/P95/P99 规划耗时。
- 简历只写实际生成并运行过的测试规模与结果；合成测试不能表述为真实生产用户日志，规划层指标不能表述为端到端回答准确率。

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
