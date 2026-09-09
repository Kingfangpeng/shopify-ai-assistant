"""知识检索、证据与引用的内部模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.documents import Document


RetrievalMode = Literal["required", "probe"]
RetrievalStatus = Literal["ready", "no_match", "unavailable"]


@dataclass(frozen=True)
class EvidenceDecision:
    documents: tuple[Document, ...]
    accepted: bool
    reason: str
    exact_identifier_match: bool = False


@dataclass(frozen=True)
class RetrievalOutcome:
    query: str
    mode: RetrievalMode
    status: RetrievalStatus
    documents: tuple[Document, ...] = ()
    citations: tuple[dict[str, Any], ...] = ()
    strategy: str = "none"
    reranker_status: str = "not_run"
    candidates: int = 0
    duration_ms: int = 0
    accepted: bool = False
    decision: str = ""
    exact_identifier_match: bool = False
