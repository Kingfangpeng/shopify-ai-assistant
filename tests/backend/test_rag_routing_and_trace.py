from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from app.agent.dispatcher import DispatchPlan
from app.core.llm_factory import llm_factory
from app.services.chat.agent_service import chat_agent_service
from app.services.retrieval.evidence_policy import evidence_policy
from app.services.retrieval.models import RetrievalOutcome
from app.services.retrieval.pipeline import retrieval_pipeline


def document(content: str, *, score: float, rank: int = 1, chunk_id: str = "doc:v1:c0") -> Document:
    return Document(page_content=content, metadata={
        "document_id": "doc",
        "file_name": "XRK-3600-manual.md",
        "version": 1,
        "chunk_id": chunk_id,
        "title": "XRK-3600 Product Specifications",
        "retrieval_rank": rank,
        "reranker_score": score,
        "reranker_status": "ready",
    })


def test_identifier_evidence_accepts_matching_product_and_rejects_substitution():
    matched = evidence_policy.select(
        "XRK-3600 的参数是什么",
        [document("XRK-3600 capacity 3840Wh", score=0.99)],
        "probe",
    )
    substituted = evidence_policy.select(
        "ZZZ-9000 的参数是什么",
        [document("XRK-3600 capacity 3840Wh", score=0.99)],
        "required",
    )

    assert matched.accepted is True
    assert matched.exact_identifier_match is True
    assert substituted.accepted is False
    assert substituted.documents == ()


def test_probe_rejects_high_scoring_document_without_lexical_evidence():
    decision = evidence_policy.select(
        "怎么做员工绩效考核",
        [document("XRK-3600 portable battery specifications", score=0.99)],
        "probe",
    )
    assert decision.accepted is False


def test_identifier_evidence_still_requires_a_minimum_document_score():
    decision = evidence_policy.select(
        "XRK-3600 的参数是什么",
        [document("XRK-3600 only appears in an unrelated footer", score=0.01)],
        "required",
    )
    assert decision.accepted is False
    assert decision.documents == ()


def test_required_evidence_never_reports_accepted_with_an_empty_selection():
    decision = evidence_policy.select(
        "退款政策是什么",
        [document("退款政策适用于收到商品后的三十天内", score=0.01)],
        "required",
    )
    assert decision.accepted is False
    assert decision.documents == ()


@pytest.mark.asyncio
async def test_chat_route_probes_knowledge_once_and_streams_same_citation(monkeypatch):
    doc = document("XRK-3600 capacity 3840Wh", score=0.99)
    outcome = RetrievalOutcome(
        query="XRK-3600 的参数是什么",
        mode="probe",
        status="ready",
        documents=(doc,),
        citations=({
            "document_id": "doc", "file_name": "XRK-3600-manual.md", "version": 1,
            "chunk_id": "doc:v1:c0", "title": "Product Specifications", "rank": 1,
            "score": 0.99, "snippet": "XRK-3600 capacity 3840Wh",
        },),
        strategy="rrf+flashrank",
        reranker_status="ready",
        candidates=12,
        duration_ms=8,
        accepted=True,
        decision="命中型号",
        exact_identifier_match=True,
    )
    retrieve = AsyncMock(return_value=outcome)
    monkeypatch.setattr(retrieval_pipeline, "retrieve", retrieve)

    async def resolve(*_args, **_kwargs):
        return DispatchPlan((), False, "模型误判为普通问答", "semantic_tool_call", "chat")

    class Chunk:
        content = "容量为 3840Wh【XRK-3600-manual.md v1 doc:v1:c0】"

    class Model:
        async def astream(self, _messages):
            yield Chunk()

    monkeypatch.setattr(chat_agent_service, "resolve_plan", resolve)
    monkeypatch.setattr(llm_factory, "create_chat_model", lambda **_kwargs: Model())

    events = [event async for event in chat_agent_service.query_stream(
        "XRK-3600 的参数是什么", [], "local-model", user_id="user-1",
    )]
    complete = next(event["data"] for event in events if event["type"] == "complete")
    stages = [event.get("stage") for event in events if event["type"] == "activity"]

    retrieve.assert_awaited_once_with("XRK-3600 的参数是什么", "user-1", "probe")
    assert complete["source"] == "knowledge_and_model"
    assert complete["route"] == "chat"
    assert complete["citations"][0]["cited"] is True
    assert {"route_completed", "retrieval_started", "retrieval_completed", "rerank_completed", "citation_checked"}.issubset(stages)
    assert complete["trace"]
