"""本地 FlashRank 精排；失败时由调用方显式保留 RRF 结果。"""

from __future__ import annotations

from pathlib import Path
import re
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
            # 商品型号、SKU、订单号等精确标识通常由 RRF 首位命中。只有查询标识
            # 确实出现在首条文档时才保留锚点，普通语义查询仍完全按 FlashRank 排序。
            exact_ids = {
                value.casefold() for value in re.findall(r"(?iu)\b(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)+|\b[a-z]+\d+[a-z0-9-]*\b", query)
            }
            first_text = " ".join((
                documents[0].page_content,
                *(str(value) for value in documents[0].metadata.values()),
            )).casefold()
            should_anchor = bool(exact_ids and any(value in first_text for value in exact_ids))
            anchored = ([item for item in ranked if int(item["id"]) == 0] if should_anchor else [])
            anchored.extend(
                item for item in ranked
                if not should_anchor or int(item["id"]) != 0
            )
            output: list[Document] = []
            for position, item in enumerate(anchored[:top_n], 1):
                source = documents[int(item["id"])]
                metadata = dict(source.metadata)
                metadata.update({
                    "retrieval_rank": position,
                    "reranker_rank": next(
                        rank for rank, ranked_item in enumerate(ranked, 1)
                        if int(ranked_item["id"]) == int(item["id"])
                    ),
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
