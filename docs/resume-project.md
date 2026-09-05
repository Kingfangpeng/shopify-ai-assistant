# Shopify AI Assistant — 简历项目描述

> 适用岗位方向：LLM 应用工程师 / AI Agent 开发工程师 / Python 后端工程师（FastAPI）/ 全栈工程师
> 技术栈：FastAPI · LangChain · LangGraph · httpx · SQLAlchemy · Alembic · Milvus · React(Vite)
> 说明：以下描述均来自实际代码实现，未杜撰用户量/营收等无法核实的指标。投递时按目标岗位截取对应小节即可。

---

## 一、标准版（通用项目条目）

**Shopify AI Assistant｜本地优先的 Shopify 商家运营智能体**　角色：核心开发（独立完成全栈）
*2026*

- 从零构建一套**本地优先、只读安全**的 Shopify 商家运营台：管理员登录后可用自然语言查询真实经营数据，并基于本地知识库做 RAG 问答。
- 设计**双 Agent 架构**：① 聊天 Agent 由模型提交受 Schema 约束的语义计划，再经只读工具白名单校验和服务端参数生成后执行；② 运营诊断 Agent 基于 LangGraph 实现 Plan→Execute→Replan 多步循环，处理"退款率为何上升"等复杂归因。
- 封装 **Shopify Admin GraphQL（2026-07）只读集成**，实现 17 个业务与分析工具（订单 / 弃购 / 库存 / 产品 / 客户 / 退款 / 折扣 / 明细 / 流量与 Web 性能等），统一分页、金额币种与权限错误，并按**店铺 IANA 时区**解析相对日期，避免本机时区偏差。
- 构建 **RAG 知识库**：Milvus 向量检索 + 文档切片 + 7 天回收站生命周期，上传做 SHA-256 去重、UTF-8 校验与失败回滚；将外部资料标记为**不可信内容**隔离进 `<knowledge>` 标签，不进入 system prompt，防止越权改写系统规则。
- 确立**抗幻觉与安全边界**：未配置真实凭据绝不伪造数据（`SHOPIFY_DEMO_MODE` 仅返回 `source=demo`）；鉴权用 Argon2id + HttpOnly/SameSite=Strict Cookie + 服务端会话 + CSRF + 登录限流；统一错误结构，绝不向前端泄漏异常/路径/凭据。
- 以 **SSE 流式**返回工具轨迹与数据来源（`source` 区分 `shopify_graphql` / `demo`），前端 React SPA 实时呈现，提升可解释性与信任度。

---

## 二、按岗位定制的话术

### 2.1 投递「LLM 应用工程师」
- 实现 RAG 全流程：相似度检索（`rag_top_k`）+ 历史上下文截断（≤12 条 / ≤8000 字符）+ 不可信资料隔离，在"给模型足够上下文"与"防止提示注入"之间取得平衡。
- 设计"确定性优先"的合成策略：出现分析/策略类意图或命中多工具时，才将真实 JSON 结果交 LLM 综合，并强制约束"只依据实时数据、不编造数字"。
- 用 LangGraph 落地 Plan-Execute-Replan 深度 Agent，处理需要多步工具调用的经营诊断，可讲 planner/executor/replanner 三节点闭环与重规划触发条件。

### 2.2 投递「AI Agent / 智能体开发工程师」
- 8 个只读 Shopify 工具经 `app/tools/shopify_tool.py` 适配为 LangChain tool，纳入工具白名单。
- 关键设计：**模型负责理解，程序负责授权**。模型只能提交限定 route 和 0–4 个工具名的结构化计划；服务端验证允许列表并生成日期/筛选参数，不允许模型直接执行任意 GraphQL。
- 可深入讲 `semantic_planner`（语义理解）→ `dispatcher`（只读验证与执行）→ `requires_analysis`（确定性格式化或模型综合）的分支逻辑；规划失败时明确报错且不执行任何业务查询。

### 2.3 投递「Python 后端工程师（FastAPI）」
- 后端分层：入口 `main.py` 挂 CORS / TrustedHost / RequestSecurity(Origin-Host 校验) 三层中间件；业务路由统一 `Depends(get_current_user)`。
- 集成层解耦为 client / service / tools 三层：`client` 管 HTTP 与节流（429/THROTTLED 重试），`service` 管领域聚合，`tools` 管 Agent 适配，便于单测与维护。
- 数据层：SQLite 存元数据/会话/审计，Milvus 存向量，DB schema 变更走 **Alembic 迁移**，禁用 `create_all` 改表，保证可回滚。

### 2.4 投递「全栈工程师」
- 后端 FastAPI + 前端 React(Vite) SPA（Login / Knowledge / Chat / History / Settings 五页），前后端通过 SSE 流式联调。
- 强调你既写 Agent 编排与 GraphQL 集成，也负责前端页面与流式交互，能独立交付端到端功能。

---

## 三、面试官可能追问 & 应对要点

| 追问 | 建议回答口径 |
|------|--------------|
| 能否扛生产流量 / 高并发？ | 这是本地敏感数据场景的**刻意取舍**：单机单管理员、只读、不暴露公网，安全优先于扩展；若要上云可拆为无状态服务 + 托管向量库 + 多租户鉴权。 |
| 如何避免让 LLM 自由调用工具带来的风险？ | LLM 只提交严格 Schema 的意图计划；服务端校验只读允许列表、最多 4 个工具和参数边界。模型负责理解自然语言，程序负责权限和执行。 |
| 知识库资料不可信，那 RAG 有什么用？ | 资料作为**补充证据**进入 `<knowledge>` 标签供模型参考，但被显式约束"不改变系统规则、不触发写操作"，在可用性与防注入之间取平衡。 |
| 没有模型微调，价值在哪？ | 价值在**应用层编排与工程化**：工具治理、安全边界、抗幻觉、可解释流式——这些是把 LLM 做成可靠产品的关键，而非训练模型本身。 |

---

## 四、可量化的工程事实（用于支撑表述，非用户指标）

- Shopify 集成版本固定：`2026-07`
- Shopify 只读工具：17 个
- 单指标分页上限：25000 条
- 相对日期窗口上限：90 天
- 聊天历史截断：≤12 条 / ≤8000 字符
- 并发工具调用上限：4 个
- 知识库回收站保留期：7 天
- 绑定地址：仅 `127.0.0.1:9901`
- 密码哈希：Argon2id；会话：服务端不透明 token + HttpOnly + SameSite=Strict
