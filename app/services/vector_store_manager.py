"""Milvus 稠密向量与 BM25 混合检索、RRF 融合及影子集合切换。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import List
from uuid import uuid4

from langchain_core.documents import Document
from langchain_milvus import BM25BuiltInFunction, Milvus
from loguru import logger
from pymilvus import AnnSearchRequest, MilvusClient, RRFRanker, connections

from app.config import config
from app.services.reranker_service import reranker_service
from app.services.vector_embedding_service import vector_embedding_service
from app.core.milvus_client import _patch_pymilvus_milvus_client_orm_alias


@dataclass(frozen=True)
class RetrievalResult:
    documents: list[Document]
    strategy: str
    reranker_status: str
    candidates: int


class VectorStoreManager:
    def __init__(self, collection_name: str | None = None, alias_name: str | None = None) -> None:
        self.vector_store: Milvus | None = None
        self.collection_name = collection_name or config.milvus_collection
        self.alias_name = config.milvus_collection_alias if alias_name is None and collection_name is None else alias_name
        self._lock = Lock()

    @property
    def _uri(self) -> str:
        return f"http://{config.milvus_host}:{config.milvus_port}"

    def _physical_or_alias(self) -> str:
        client = MilvusClient(uri=self._uri, timeout=config.milvus_timeout / 1000)
        try:
            if self.alias_name:
                try:
                    target = client.describe_alias(self.alias_name).get("collection")
                    if target:
                        return self.alias_name
                except Exception:
                    pass
            return self.collection_name
        finally:
            client.close()

    @staticmethod
    def _bm25() -> BM25BuiltInFunction:
        # jieba 保留中文边界；lowercase 统一英文型号但不会丢弃 SKU 与数字。
        return BM25BuiltInFunction(
            input_field_names="content",
            output_field_names="sparse",
            analyzer_params={"tokenizer": "jieba", "filter": ["lowercase"]},
        )

    def _make_store(self, collection_name: str, *, drop_old: bool = False) -> Milvus:
        _patch_pymilvus_milvus_client_orm_alias()
        if not connections.has_connection("default"):
            connections.connect(
                alias="default",
                host=config.milvus_host,
                port=str(config.milvus_port),
                timeout=config.milvus_timeout / 1000,
            )
        return Milvus(
            embedding_function=vector_embedding_service,
            builtin_function=self._bm25(),
            collection_name=collection_name,
            connection_args={"uri": self._uri},
            auto_id=False,
            drop_old=drop_old,
            text_field="content",
            vector_field=["dense", "sparse"],
            primary_field="id",
            metadata_field="metadata",
            index_params=[
                {"metric_type": "COSINE", "index_type": "HNSW", "params": {"M": 16, "efConstruction": 64}},
                {"metric_type": "BM25", "index_type": "SPARSE_INVERTED_INDEX", "params": {"inverted_index_algo": "DAAT_MAXSCORE"}},
            ],
            search_params=[
                {"metric_type": "COSINE", "params": {"ef": 64}},
                {"metric_type": "BM25", "params": {}},
            ],
        )

    def connect(self) -> Milvus:
        if self.vector_store is not None:
            return self.vector_store
        with self._lock:
            if self.vector_store is None:
                self.vector_store = self._make_store(self._physical_or_alias())
        return self.vector_store

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _user_expr(user_id: str | None) -> str | None:
        if not user_id:
            return None
        return f'metadata["user_id"] == "{VectorStoreManager._escape(user_id)}"'

    def add_documents(self, documents: List[Document], ids: list[str] | None = None) -> List[str]:
        if not documents:
            return []
        generated_ids = ids or [str(uuid4()) for _ in documents]
        result = list(self.connect().add_documents(documents, ids=generated_ids))
        self._ensure_initial_alias()
        return result

    def _ensure_initial_alias(self) -> None:
        if not self.alias_name:
            return
        client = MilvusClient(uri=self._uri, timeout=config.milvus_timeout / 1000)
        try:
            try:
                client.describe_alias(self.alias_name)
            except Exception:
                client.create_alias(collection_name=self.collection_name, alias=self.alias_name)
        finally:
            client.close()

    def delete_document_version(self, document_id: str, version: int | None = None) -> int:
        collection = self._collection()
        expr = f'metadata["document_id"] == "{self._escape(document_id)}"'
        if version is not None:
            expr += f' and metadata["version"] == {int(version)}'
        result = collection.delete(expr)
        return int(getattr(result, "delete_count", 0) or 0)

    def search(self, query: str, k: int = 5, user_id: str | None = None) -> RetrievalResult:
        safe_k = max(1, min(k, config.rag_top_k))
        had_connection = self.vector_store is not None
        try:
            pairs = self._hybrid_search(query, user_id, safe_k)
        except Exception:
            self.reset_connection()
            if not had_connection:
                raise
            logger.warning("Milvus 既有连接失效，正在重连并重试一次")
            pairs = self._hybrid_search(query, user_id, safe_k)
        candidates = []
        for position, (document, score) in enumerate(pairs[:config.rag_fusion_top_k], 1):
            metadata = dict(document.metadata)
            metadata.update({"rrf_rank": position, "rrf_score": float(score), "retrieval_strategy": "rrf"})
            candidates.append(Document(page_content=document.page_content, metadata=metadata))
        documents, reranker_status = reranker_service.rerank(query, candidates, safe_k)
        strategy = "rrf+flashrank" if reranker_status == "ready" else "rrf"
        return RetrievalResult(documents, strategy, reranker_status, len(candidates))

    def _hybrid_search(self, query: str, user_id: str | None, fallback_k: int):
        store = self.connect()
        if hasattr(store, "similarity_search_with_score"):
            return list(store.similarity_search_with_score(
                query,
                k=config.rag_fusion_top_k,
                fetch_k=max(config.rag_dense_top_k, config.rag_sparse_top_k),
                expr=self._user_expr(user_id),
                ranker_type="rrf",
                ranker_params={"k": 60},
            ))
        return [(item, 0.0) for item in store.similarity_search(query, k=fallback_k)]

    def similarity_search(self, query: str, k: int = 5, user_id: str | None = None) -> List[Document]:
        return self.search(query, k, user_id).documents

    def evaluate_search(
        self,
        query: str,
        mode: str,
        k: int = 10,
        user_id: str | None = None,
    ) -> list[Document]:
        """评估专用检索入口，固定支持 dense/bm25/rrf/rrf+flashrank 四组。"""
        if mode == "rrf+flashrank":
            return self.search(query, min(k, config.rag_top_k), user_id).documents
        if mode not in {"dense", "bm25", "rrf"}:
            raise ValueError("未知检索模式")
        store = self.connect()
        requests = []
        if mode in {"dense", "rrf"}:
            requests.append(AnnSearchRequest(
                data=[vector_embedding_service.embed_query(query)],
                anns_field="dense",
                param={"metric_type": "COSINE", "params": {"ef": 64}},
                limit=config.rag_dense_top_k,
                expr=self._user_expr(user_id),
            ))
        if mode in {"bm25", "rrf"}:
            requests.append(AnnSearchRequest(
                data=[query],
                anns_field="sparse",
                param={"metric_type": "BM25", "params": {}},
                limit=config.rag_sparse_top_k,
                expr=self._user_expr(user_id),
            ))
        raw = store.client.hybrid_search(
            collection_name=store.collection_name,
            reqs=requests,
            ranker=RRFRanker(60),
            limit=max(1, min(k, 20)),
            output_fields=["content", "metadata"],
        )
        documents = []
        for rank, hit in enumerate((raw[0] if raw else []), 1):
            entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
            metadata = dict(entity.get("metadata") or {})
            metadata.update({
                "retrieval_rank": rank,
                "retrieval_score": float(hit.get("distance", 0) if isinstance(hit, dict) else getattr(hit, "distance", 0)),
                "retrieval_strategy": mode,
            })
            documents.append(Document(page_content=str(entity.get("content") or ""), metadata=metadata))
        if mode == "rrf":
            return documents
        return documents[:k]

    def rebuild_shadow(self, documents: list[Document], smoke_query: str = "商品") -> dict:
        if not documents:
            raise ValueError("影子集合不能为空")
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        shadow = f"{config.milvus_collection}_shadow_{timestamp}"
        store = self._make_store(shadow, drop_old=False)
        store.add_documents(documents, ids=[str(uuid4()) for _ in documents])
        verification = store.similarity_search_with_score(
            smoke_query,
            k=1,
            fetch_k=4,
            ranker_type="rrf",
            ranker_params={"k": 60},
        )
        if not verification:
            raise RuntimeError("影子集合验证失败，未切换别名")
        client = MilvusClient(uri=self._uri, timeout=config.milvus_timeout / 1000)
        previous = None
        try:
            try:
                previous = client.describe_alias(config.milvus_collection_alias).get("collection")
                client.alter_alias(collection_name=shadow, alias=config.milvus_collection_alias)
            except Exception:
                client.create_alias(collection_name=shadow, alias=config.milvus_collection_alias)
        finally:
            client.close()
        with self._lock:
            self.vector_store = self._make_store(config.milvus_collection_alias)
        return {"collection": shadow, "previous_collection": previous, "chunks": len(documents), "verified": True}

    def reset_connection(self) -> None:
        with self._lock:
            self.vector_store = None

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
                "chunk_id": meta.get("chunk_id", row.get("id", "")),
                "document_id": document_id,
                "version": meta.get("version"),
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
        store = self.connect()
        if store.col is None:
            raise RuntimeError("Milvus Collection 未初始化")
        return store.col

    def get_vector_store(self) -> Milvus:
        return self.connect()


vector_store_manager = VectorStoreManager()
