import asyncio
from pathlib import Path

import pytest

from app.agent.dispatcher import DispatchPlan
from scripts.evaluate_tool_routing import (
    EvaluationResult, calculate_metrics, chat_agent_service, evaluate_case, load_cases,
    load_suite_manifest,
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


def test_product_identifier_routing_dataset_covers_route_boundaries():
    path = Path(__file__).parents[1] / "fixtures" / "rag_product_identifier_routing.json"
    cases = load_cases(path)
    assert len(cases) == 12
    assert {case["expected_route"] for case in cases} == {
        "knowledge", "shopify", "mixed", "unsupported", "chat",
    }
    assert len({case["question"] for case in cases}) == len(cases)


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


def test_production_suite_manifest_loads_all_unique_cases():
    path = Path(__file__).parents[1] / "fixtures" / "evaluation" / "manifest.json"
    cases, source = load_suite_manifest(path)
    assert len(cases) == 1500
    assert len({case["id"] for case in cases}) == 1500
    assert len({case["question"] for case in cases}) == 1500
    assert source["suite_version"] == "routing-production-v1"
    assert len(source["files"]) == 5


def test_metrics_include_routes_percentiles_and_repeat_stability():
    first = _result(expected=("get_orders_summary",), actual=("get_orders_summary",), exact=True)
    same = _result(expected=("get_orders_summary",), actual=("get_orders_summary",), exact=True)
    changed_first = _result(expected=("get_orders_summary",), actual=("get_orders_summary",), exact=True)
    changed_second = _result(expected=("get_orders_summary",), actual=(), exact=False)
    first = EvaluationResult(**{**first.__dict__, "case_id": "stable", "expected_route": "shopify", "route": "shopify", "elapsed_ms": 10})
    same = EvaluationResult(**{**same.__dict__, "case_id": "stable", "expected_route": "shopify", "route": "shopify", "elapsed_ms": 20})
    changed_first = EvaluationResult(**{**changed_first.__dict__, "case_id": "changed", "expected_route": "shopify", "route": "shopify", "elapsed_ms": 30})
    changed_second = EvaluationResult(**{**changed_second.__dict__, "case_id": "changed", "expected_route": "shopify", "route": "chat", "elapsed_ms": 40})
    metrics = calculate_metrics([first, same, changed_first, changed_second])
    assert metrics["route_accuracy"] == 3 / 4
    assert metrics["route_confusion_matrix"] == {"shopify": {"chat": 1, "shopify": 3}}
    assert metrics["p50_latency_ms"] == 30
    assert metrics["p95_latency_ms"] == 40
    assert metrics["repeat_stability"] == 0.5


def test_single_run_does_not_claim_repeat_stability():
    metrics = calculate_metrics([_result(expected=(), actual=(), exact=True)])
    assert metrics["repeat_stability"] is None
    assert metrics["repeated_cases"] == 0


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
