# 代码结构与边界

目录和模块边界以 [PLAN.md](./PLAN.md) 为准。

## 后端调用链

```text
HTTP / SSE
  → app/api（鉴权、校验、响应映射）
  → app/services（聊天或知识库业务事务）
  → app/db（SQLite 元数据）/ Milvus（向量）

Agent
  → app/tools（只读工具白名单）
  → app/integrations/shopify（GraphQL 协议与业务聚合）
```

- `app/integrations/shopify/client.py` 只负责域名校验、HTTP、GraphQL 错误、节流与重试。
- `app/integrations/shopify/service.py` 负责八项只读业务指标，所有日期过滤必须在这里落实。
- `app/services/knowledge/service.py` 是文件与向量生命周期的唯一写入口；API 和 Agent 不得直接操作本机路径。
- `app/services/chat/service.py` 强制校验会话所有者，并限制 RAG 历史为最近 12 条、最多 8000 字符。
- `app/auth/` 负责密码、会话、CSRF 与请求安全；浏览器不得持久化登录令牌。

## 新增代码要求

- 业务 API 默认挂在认证依赖后；只有 `/health` 和 `/api/auth/login` 可公开访问。
- 错误必须转换为 `{"error":{"code","message","request_id"}}`，禁止把异常、绝对路径或凭据返回前端。
- 新 Shopify 工具必须只读，并先在聚合服务中实现和测试，再包装为 LangChain 工具。
- 知识文档始终是不可信资料，只能进入普通消息或 ToolMessage，不能拼入 system prompt。
- 数据库变更必须新增 Alembic 迁移，不能依赖 `create_all` 修改既有表。
