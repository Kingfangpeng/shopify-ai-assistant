"""本地 FlashRank 精排；失败时由调用方显式保留 RRF 结果。"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from langchain_core.documents import Document
from loguru import logger

from app.config import config


class RerankerService:
    def __init__(self) -> None:
        self._ranker = None
        self._lock = Lock()

    def _load(self):  # type: ignore[no-untyped-def]
        if self._ranker is not None:
            return self._ranker
        with self._lock:
            if self._ranker is None:
                from flashrank import Ranker
                model_path = Path(config.reranker_cache_dir) / config.reranker_model
                if not model_path.is_dir():
                    raise RuntimeError(
                        "FlashRank 模型尚未缓存；请先执行 python -m app.cli prefetch-reranker"
                    )
                self._ranker = Ranker(
                    model_name=config.reranker_model,
                    cache_dir=config.reranker_cache_dir,
                    max_length=config.reranker_max_length,
                    log_level="WARNING",
                )
        return self._ranker

    def rerank(self, query: str, documents: list[Document], top_n: int) -> tuple[list[Document], str]:
        if not config.reranker_enabled or not documents:
            return documents[:top_n], "disabled"
        try:
            from flashrank import RerankRequest
            passages = [
                {"id": index, "text": document.page_content, "meta": document.metadata}
                for index, document in enumerate(documents)
            ]
            ranked = self._load().rerank(RerankRequest(query=query, passages=passages))
            output: list[Document] = []
            for position, item in enumerate(ranked[:top_n], 1):
                source = documents[int(item["id"])]
                metadata = dict(source.metadata)
                metadata.update({
                    "retrieval_rank": position,
                    "reranker_score": float(item.get("score") or 0),
                    "retrieval_strategy": "rrf+flashrank",
                    "reranker_status": "ready",
                })
                output.append(Document(page_content=source.page_content, metadata=metadata))
            return output, "ready"
        except Exception as exc:
            logger.warning("FlashRank 不可用，显式降级为 RRF: {}", type(exc).__name__)
            output = []
            for position, source in enumerate(documents[:top_n], 1):
                metadata = dict(source.metadata)
                metadata.update({
                    "retrieval_rank": position,
                    "retrieval_strategy": "rrf",
                    "reranker_status": "unavailable",
                })
                output.append(Document(page_content=source.page_content, metadata=metadata))
            return output, "unavailable"

    def reset(self) -> None:
        with self._lock:
            self._ranker = None


reranker_service = RerankerService()
