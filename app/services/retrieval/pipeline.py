"""复用一次混合检索结果生成回答证据、引用与公开统计。"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from loguru import logger

from app.config import config
from app.services.retrieval.evidence_policy import evidence_policy
from app.services.retrieval.models import RetrievalMode, RetrievalOutcome
from app.services.vector_store_manager import vector_store_manager


def _safe_text(value: Any, limit: int) -> str:
    clean = "".join(char for char in str(value or "") if char in "\n\t" or ord(char) >= 32)
    return clean[:limit]


def citation(document) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    metadata = document.metadata
    content = " ".join(document.page_content.split())
    score = metadata.get("reranker_score", metadata.get("rrf_score"))
    try:
        safe_score = round(float(score), 6) if score is not None else None
    except (TypeError, ValueError):
        safe_score = None
    rank = metadata.get("retrieval_rank") or metadata.get("rrf_rank")
    return {
        "document_id": _safe_text(metadata.get("document_id"), 100),
        "file_name": _safe_text(metadata.get("file_name") or "未知来源", 255),
        "version": metadata.get("version"),
        "chunk_id": _safe_text(metadata.get("chunk_id"), 160),
        "title": _safe_text(metadata.get("title") or metadata.get("h2") or metadata.get("h1"), 255),
        "rank": int(rank) if isinstance(rank, (int, float)) else None,
        "score": safe_score,
        "snippet": _safe_text(content, 320),
    }


class RetrievalPipeline:
    async def retrieve(self, query: str, user_id: str | None, mode: RetrievalMode) -> RetrievalOutcome:
        started = perf_counter()
        try:
            result = await asyncio.to_thread(
                vector_store_manager.search, query, config.rag_top_k, user_id,
            )
            decision = evidence_policy.select(query, result.documents, mode)
            documents = decision.documents if decision.accepted else ()
            return RetrievalOutcome(
                query=query,
                mode=mode,
                status="ready" if decision.accepted else "no_match",
                documents=documents,
                citations=tuple(citation(document) for document in documents),
                strategy=result.strategy,
                reranker_status=result.reranker_status,
                candidates=result.candidates,
                duration_ms=round((perf_counter() - started) * 1000),
                accepted=decision.accepted,
                decision=decision.reason,
                exact_identifier_match=decision.exact_identifier_match,
            )
        except Exception as exc:
            logger.warning("知识检索 Pipeline 不可用: {}", type(exc).__name__)
            return RetrievalOutcome(
                query=query,
                mode=mode,
                status="unavailable",
                duration_ms=round((perf_counter() - started) * 1000),
                decision="知识库依赖不可用",
            )


retrieval_pipeline = RetrievalPipeline()
