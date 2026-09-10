"""把检索候选转换为可以进入回答上下文的证据。"""

from __future__ import annotations

import re
import unicodedata

from langchain_core.documents import Document

from app.config import config
from app.services.retrieval.models import EvidenceDecision, RetrievalMode


ALNUM_TOKEN = re.compile(r"(?iu)[a-z0-9][a-z0-9_-]{2,}")
IDENTIFIER = re.compile(r"(?iu)(?=[a-z0-9_-]*[a-z])(?=[a-z0-9_-]*\d)[a-z0-9][a-z0-9_-]{2,}")
HAN_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
COMMON_TOKENS = {
    "what", "which", "this", "that", "with", "from", "about", "please", "parameters",
    "参数", "什么", "哪些", "多少", "一下", "这个", "那个", "产品", "资料", "文档", "上传",
}


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").casefold()


def identifiers(value: str) -> set[str]:
    return {token.replace("_", "-") for token in IDENTIFIER.findall(normalize_text(value))}


def lexical_tokens(value: str) -> set[str]:
    normalized = normalize_text(value)
    tokens = {
        token.replace("_", "-") for token in ALNUM_TOKEN.findall(normalized)
        if token not in COMMON_TOKENS
    }
    for run in HAN_RUN.findall(normalized):
        tokens.update(run[index:index + 2] for index in range(len(run) - 1))
    return tokens - COMMON_TOKENS


def document_text(document: Document) -> str:
    metadata = document.metadata
    return " ".join((
        document.page_content,
        str(metadata.get("file_name") or ""),
        str(metadata.get("title") or ""),
        str(metadata.get("h1") or ""),
        str(metadata.get("h2") or ""),
    ))


def reranker_score(document: Document) -> float | None:
    value = document.metadata.get("reranker_score")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class EvidencePolicy:
    """优先保护产品型号，同时拒绝向普通聊天注入伪相关片段。"""

    def select(self, query: str, documents: list[Document], mode: RetrievalMode) -> EvidenceDecision:
        if not documents:
            return EvidenceDecision((), False, "检索没有返回候选")

        query_ids = identifiers(query)
        matched_ids = {
            identifier
            for identifier in query_ids
            if any(identifier in normalize_text(document_text(document)).replace("_", "-") for document in documents)
        }
        if matched_ids:
            selected = self._select_ranked(documents, config.rag_identifier_document_min_score)
            return EvidenceDecision(
                tuple(selected),
                bool(selected),
                f"知识片段命中型号：{', '.join(sorted(matched_ids))}",
                True,
            )

        # 问题包含明确型号但候选完全没有该型号时，不能用相似产品顶替。
        if query_ids:
            return EvidenceDecision((), False, "候选未命中问题中的产品型号")

        query_terms = lexical_tokens(query)
        lexical_match = any(query_terms.intersection(lexical_tokens(document_text(document))) for document in documents)
        scores = [score for document in documents if (score := reranker_score(document)) is not None]
        top_score = max(scores, default=None)

        if mode == "probe":
            accepted = bool(
                lexical_match
                and top_score is not None
                and top_score >= config.rag_probe_min_score
            )
            reason = (
                "本地证据通过普通问答探测门槛"
                if accepted else "本地候选未通过普通问答证据门槛"
            )
        else:
            # 明确要求读资料且问题没有具体型号时，保留 RRF 降级能力；有精排分数时仍设最低门槛。
            accepted = bool(
                lexical_match
                or top_score is None
                or top_score >= config.rag_required_min_score
            )
            reason = "知识证据通过必需检索门槛" if accepted else "候选与资料问题相关性不足"

        if not accepted:
            return EvidenceDecision((), False, reason)
        selected = self._select_ranked(documents, config.rag_selected_document_min_score)
        if not selected:
            return EvidenceDecision((), False, "候选通过初筛，但没有片段达到入模门槛")
        return EvidenceDecision(
            tuple(selected),
            True,
            reason,
        )

    @staticmethod
    def _select_ranked(documents: list[Document], minimum_score: float) -> list[Document]:
        selected = [
            document for document in documents
            if (score := reranker_score(document)) is None or score >= minimum_score
        ]
        return selected[:5]


evidence_policy = EvidencePolicy()
