"""Milvus vector store manager."""

from typing import List

from langchain_core.documents import Document
from langchain_milvus import Milvus
from loguru import logger

from app.config import config
from app.core.milvus_client import milvus_manager
from app.services.vector_embedding_service import vector_embedding_service

COLLECTION_NAME = config.milvus_collection


class VectorStoreManager:
    """Wrapper around the Milvus vector store used by the knowledge base."""

    def __init__(self):
        self.vector_store = None
        self.collection_name = COLLECTION_NAME
        self._initialize_vector_store()

    def _initialize_vector_store(self):
        try:
            _ = milvus_manager.connect()

            connection_args = {
                "host": config.milvus_host,
                "port": config.milvus_port,
            }

            self.vector_store = Milvus(
                embedding_function=vector_embedding_service,
                collection_name=self.collection_name,
                connection_args=connection_args,
                auto_id=False,
                drop_old=False,
                text_field="content",
                vector_field="vector",
                primary_field="id",
                metadata_field="metadata",
            )

            logger.info(
                f"VectorStore initialized at {config.milvus_host}:{config.milvus_port}, "
                f"collection={self.collection_name}"
            )

        except Exception as e:
            logger.error(f"VectorStore initialization failed: {e}")
            raise

    @staticmethod
    def _escape_expr_value(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def add_documents(self, documents: List[Document]) -> List[str]:
        try:
            import time
            import uuid

            start_time = time.time()
            ids = [str(uuid.uuid4()) for _ in documents]
            result_ids = self.vector_store.add_documents(documents, ids=ids)
            elapsed = time.time() - start_time
            logger.info(f"Added {len(documents)} documents to VectorStore in {elapsed:.2f}s")
            return result_ids
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            raise

    def delete_by_source(self, file_path: str) -> int:
        try:
            collection = milvus_manager.get_collection()
            safe_path = self._escape_expr_value(file_path)
            expr = f'metadata["_source"] == "{safe_path}"'
            result = collection.delete(expr)
            deleted_count = result.delete_count if hasattr(result, "delete_count") else 0
            logger.info(f"Deleted old source data: {file_path}, count={deleted_count}")
            return deleted_count
        except Exception as e:
            logger.warning(f"Failed to delete old source data, possibly first indexing run: {e}")
            return 0

    def delete_by_file(self, file_path: str) -> int:
        """Delete chunks by exact source path or uploaded file name."""
        try:
            collection = milvus_manager.get_collection()
            safe_value = self._escape_expr_value(file_path)
            deleted_count = 0

            for expr in (
                f'metadata["_source"] == "{safe_value}"',
                f'metadata["_file_name"] == "{safe_value}"',
            ):
                result = collection.delete(expr)
                deleted_count += result.delete_count if hasattr(result, "delete_count") else 0

            logger.info(f"Deleted knowledge file: {file_path}, count={deleted_count}")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete knowledge file {file_path}: {e}")
            raise

    def get_vector_store(self) -> Milvus:
        return self.vector_store

    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        try:
            docs = self.vector_store.similarity_search(query, k=k)
            logger.debug(f"Similarity search complete: query={query!r}, count={len(docs)}")
            return docs
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []

    def list_chunks(
        self,
        file_path: str | None = None,
        filename: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Query stored document chunks with optional file filtering and pagination."""
        try:
            collection = milvus_manager.get_collection()
            safe_limit = max(1, min(int(limit), 500))
            safe_offset = max(0, int(offset))

            if file_path:
                expr = f'metadata["_source"] == "{self._escape_expr_value(file_path)}"'
            elif filename:
                expr = f'metadata["_file_name"] == "{self._escape_expr_value(filename)}"'
            else:
                expr = 'id != ""'

            results = collection.query(
                expr=expr,
                output_fields=["id", "content", "metadata"],
                limit=safe_limit + safe_offset + 1,
            )
            chunks = []
            for row in results[safe_offset:safe_offset + safe_limit]:
                meta = row.get("metadata", {})
                content = row.get("content", "")
                chunks.append(
                    {
                        "id": row.get("id", ""),
                        "file_name": meta.get("_file_name", "unknown"),
                        "source": meta.get("_source", ""),
                        "content": content,
                        "content_preview": content[:200] + ("..." if len(content) > 200 else ""),
                        "char_count": len(content),
                        "h1": meta.get("h1", ""),
                        "h2": meta.get("h2", ""),
                    }
                )

            chunks.sort(key=lambda x: (x["file_name"], x["h1"], x["h2"], x["id"]))
            return {
                "chunks": chunks,
                "limit": safe_limit,
                "offset": safe_offset,
                "has_more": len(results) > safe_offset + safe_limit,
            }
        except Exception as e:
            logger.error(f"Failed to list knowledge chunks: {e}")
            return {"chunks": [], "limit": limit, "offset": offset, "has_more": False}

    def get_stats(self) -> dict:
        """Return total chunks and per-file chunk counts."""
        try:
            collection = milvus_manager.get_collection()
            total = collection.num_entities
            results = collection.query(
                expr='id != ""',
                output_fields=["metadata"],
                limit=16384,
            )
            file_counts: dict = {}
            for row in results:
                meta = row.get("metadata", {})
                fn = meta.get("_file_name", "unknown")
                file_counts[fn] = file_counts.get(fn, 0) + 1
            files = [{"file_name": k, "chunk_count": v} for k, v in file_counts.items()]
            files.sort(key=lambda x: x["file_name"])
            return {"total_chunks": total, "files": files}
        except Exception as e:
            logger.error(f"Failed to get knowledge stats: {e}")
            return {"total_chunks": 0, "files": []}


vector_store_manager = VectorStoreManager()
