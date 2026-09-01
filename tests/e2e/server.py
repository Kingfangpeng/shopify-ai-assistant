"""E2E 专用本地服务：只替换不可用的 Milvus/LLM 外部依赖。"""

from __future__ import annotations

from app.main import app
from app.services.rag_agent_service import rag_agent_service
from app.services.vector_store_manager import vector_store_manager

stored_documents = []


def add_documents(documents, ids=None):
    stored_documents.extend(documents)
    return ids or [f"e2e-{index}" for index, _ in enumerate(documents)]


def delete_document_version(document_id, version=None):
    before = len(stored_documents)
    stored_documents[:] = [doc for doc in stored_documents if not (
        doc.metadata.get("document_id") == document_id
        and (version is None or doc.metadata.get("version") == version)
    )]
    return before - len(stored_documents)


def list_chunks(document_id, limit=50, offset=0):
    rows = [doc for doc in stored_documents if doc.metadata.get("document_id") == document_id]
    items = [{
        "id": f"e2e-{index}",
        "document_id": document_id,
        "file_name": doc.metadata.get("file_name"),
        "content": doc.page_content,
        "content_preview": doc.page_content[:200],
        "char_count": len(doc.page_content),
        "h1": doc.metadata.get("h1", ""),
        "h2": doc.metadata.get("h2", ""),
    } for index, doc in enumerate(rows[offset:offset + limit])]
    return {"items": items, "limit": limit, "offset": offset, "has_more": False}


async def query_stream(question, history):
    yield {"type": "status", "data": "正在检索知识库…"}
    answer = f"已结合本地产品资料回答：{question}。当前会话包含 {len(history)} 条历史消息。"
    yield {"type": "content", "data": answer}
    yield {"type": "complete", "data": {"answer": answer, "source": "knowledge_and_model"}}


vector_store_manager.add_documents = add_documents
vector_store_manager.delete_document_version = delete_document_version
vector_store_manager.list_chunks = list_chunks
vector_store_manager.similarity_search = lambda _query, k=3: stored_documents[:k]
rag_agent_service.query_stream = query_stream
