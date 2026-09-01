# 知识库与聊天历史

## 数据归属

- `chat_sessions` 与 `chat_messages` 保存服务端聊天历史。
- `knowledge_documents` 保存文档名、SHA-256、版本、状态和回收期限，不保存绝对路径。
- `uploads/` 保存 UUID 命名的源文件；`.trash/` 保存七天内可恢复的文件。
- Milvus 向量元数据只包含服务端 `document_id`、版本、展示文件名和标题层级。

## 接口

- `GET|POST /api/chat/sessions`
- `GET|DELETE /api/chat/sessions/{id}`
- `POST /api/chat/sessions/import`
- `POST /api/chat`、`POST /api/chat_stream`
- `GET|POST /api/knowledge/documents`
- `GET /api/knowledge/documents/{id}/chunks`
- `DELETE /api/knowledge/documents/{id}`
- `POST /api/knowledge/documents/{id}/restore`
- `POST /api/knowledge/rebuild`

旧的 `/api/index_directory` 和 `/api/upload` 不再执行操作，只返回迁移提示。客户端不能提交服务器目录或文件路径。

## 失败语义

- 新版本 Embedding 或向量写入失败时，同名旧文件与旧向量保持不变。
- Milvus 维度不匹配时拒绝知识库操作并给出维护命令，绝不自动删除 Collection。
- 检索依赖故障返回明确错误，不会伪装为“知识库为空”。
- 成功导入旧 `localStorage` 会话后，前端才清除旧缓存。
