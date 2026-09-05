import asyncio
from pathlib import Path

import pytest

from app.agent.dispatcher import DispatchPlan
from scripts.evaluate_tool_routing import (
    EvaluationResult, calculate_metrics, chat_agent_service, evaluate_case, load_cases,
)


def _result(*, expected=(), actual=(), exact=False):
    expected_set = set(expected)
    actual_set = set(actual)
    return EvaluationResult(
        case_id="case",
        category="测试",
        question="测试问题",
        expected_tools=tuple(expected),
        actual_tools=tuple(actual),
        planner="deterministic",
        exact=exact,
        missing_tools=tuple(sorted(expected_set - actual_set)),
        extra_tools=tuple(sorted(actual_set - expected_set)),
        elapsed_ms=1,
    )


def test_tool_routing_dataset_is_valid_and_has_boundary_cases():
    path = Path(__file__).parents[1] / "fixtures" / "tool_routing_cases.json"
    cases = load_cases(path)
    assert len(cases) >= 40
    assert any(case["history"] for case in cases if "history" in case)
    assert sum(not case["expected_tools"] for case in cases) >= 8


def test_tool_routing_metrics_count_exact_precision_and_recall():
    results = [
        _result(expected=("get_orders_summary",), actual=("get_orders_summary",), exact=True),
        _result(expected=("get_refund_stats",), actual=("get_orders_summary",), exact=False),
        _result(expected=(), actual=(), exact=True),
    ]
    metrics = calculate_metrics(results)
    assert metrics["exact_accuracy"] == 2 / 3
    assert metrics["tool_precision"] == 0.5
    assert metrics["tool_recall"] == 0.5
    assert metrics["tool_f1"] == 0.5
    assert metrics["negative_accuracy"] == 1.0


@pytest.mark.asyncio
async def test_evaluation_uses_public_planner_and_counts_route_mismatch(monkeypatch):
    async def resolve(question, history, model):
        assert question == "润色附件"
        assert history == []
        assert model == "test-model"
        return DispatchPlan((), False, "测试", "semantic_tool_call", "chat")

    monkeypatch.setattr(chat_agent_service, "resolve_plan", resolve)
    result = await evaluate_case(
        {"id": "route", "question": "润色附件", "expected_tools": [], "expected_route": "knowledge"},
        "test-model", asyncio.Semaphore(1),
    )
    assert result.actual_tools == ()
    assert result.route == "chat"
    assert result.exact is False
    assert result.error is None


@pytest.mark.asyncio
async def test_planner_failure_is_not_counted_as_successful_empty_plan(monkeypatch):
    async def resolve(*_args):
        raise RuntimeError("private detail must not appear in report")

    monkeypatch.setattr(chat_agent_service, "resolve_plan", resolve)
    result = await evaluate_case(
        {"id": "failure", "question": "你好", "expected_tools": [], "expected_route": "chat"},
        "test-model", asyncio.Semaphore(1),
    )
    assert result.exact is False
    assert result.error == "RuntimeError: evaluation_failed"
    assert calculate_metrics([result])["errors"] == 1
