"""Milvus 向量存储包装：惰性连接、按服务端文档 ID 管理。"""

from __future__ import annotations

from threading import Lock
from typing import List

from langchain_core.documents import Document
from langchain_milvus import Milvus
from loguru import logger

from app.config import config
from app.core.milvus_client import milvus_manager
from app.services.vector_embedding_service import vector_embedding_service


class VectorStoreManager:
    def __init__(self) -> None:
        self.vector_store: Milvus | None = None
        self.collection_name = config.milvus_collection
        self._lock = Lock()

    def connect(self) -> Milvus:
        if self.vector_store is not None:
            return self.vector_store
        with self._lock:
            if self.vector_store is None:
                milvus_manager.connect()
                self.vector_store = Milvus(
                    embedding_function=vector_embedding_service,
                    collection_name=self.collection_name,
                    connection_args={"host": config.milvus_host, "port": config.milvus_port},
                    auto_id=False,
                    drop_old=False,
                    text_field="content",
                    vector_field="vector",
                    primary_field="id",
                    metadata_field="metadata",
                )
        return self.vector_store

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def add_documents(self, documents: List[Document], ids: list[str] | None = None) -> List[str]:
        if not documents:
            return []
        import uuid

        generated_ids = ids or [str(uuid.uuid4()) for _ in documents]
        return list(self.connect().add_documents(documents, ids=generated_ids))

    def delete_document_version(self, document_id: str, version: int | None = None) -> int:
        collection = milvus_manager.get_collection() if self.vector_store is not None else self._collection()
        expr = f'metadata["document_id"] == "{self._escape(document_id)}"'
        if version is not None:
            expr += f' and metadata["version"] == {int(version)}'
        result = collection.delete(expr)
        return int(getattr(result, "delete_count", 0) or 0)

    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        # 依赖故障必须向上传递，不能伪装成知识库为空。
        safe_k = max(1, min(k, 20))
        had_connection = self.vector_store is not None
        try:
            return list(self.connect().similarity_search(query, k=safe_k))
        except Exception:
            self.reset_connection()
            if not had_connection:
                raise
            logger.warning("Milvus 既有连接失效，正在重连并重试一次")
            return list(self.connect().similarity_search(query, k=safe_k))

    def reset_connection(self) -> None:
        """丢弃失效的 LangChain/Milvus 连接；下次操作会重新建立。"""
        with self._lock:
            self.vector_store = None
            milvus_manager.close()

    def list_chunks(self, document_id: str, limit: int = 50, offset: int = 0) -> dict:
        collection = self._collection()
        safe_limit = max(1, min(int(limit), 200))
        safe_offset = max(0, int(offset))
        expr = f'metadata["document_id"] == "{self._escape(document_id)}"'
        results = collection.query(
            expr=expr,
            output_fields=["id", "content", "metadata"],
            limit=safe_limit + safe_offset + 1,
        )
        chunks = []
        for row in results[safe_offset:safe_offset + safe_limit]:
            meta = row.get("metadata", {})
            content = row.get("content", "")
            chunks.append({
                "id": row.get("id", ""),
                "document_id": document_id,
                "file_name": meta.get("file_name", "未知文件"),
                "content": content,
                "content_preview": content[:200] + ("…" if len(content) > 200 else ""),
                "char_count": len(content),
                "h1": meta.get("h1", ""),
                "h2": meta.get("h2", ""),
            })
        return {"items": chunks, "limit": safe_limit, "offset": safe_offset,
                "has_more": len(results) > safe_offset + safe_limit}

    def _collection(self):  # type: ignore[no-untyped-def]
        self.connect()
        return milvus_manager.get_collection()

    def get_vector_store(self) -> Milvus:
        return self.connect()


vector_store_manager = VectorStoreManager()
