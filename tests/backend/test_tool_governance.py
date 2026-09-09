import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.semantic_planner import SemanticToolPlanner
from app.agent.tool_registry import TOOL_SPEC_REGISTRY, tool_catalog_hash
from app.agent.dispatcher import DispatchPlan, LOCAL_TOOL_REGISTRY, read_only_tool_dispatcher
from mcp_servers.shopify_server import mcp


def test_tool_registry_contains_exactly_seventeen_versioned_shopify_tools():
    assert len(TOOL_SPEC_REGISTRY) == 17
    assert all(spec.version == "1.0.0" for spec in TOOL_SPEC_REGISTRY.values())
    assert len(tool_catalog_hash()) == 64


@pytest.mark.parametrize("name,arguments", [
    ("get_order_list", {"limit": 101}),
    ("get_product_performance", {"top_n": 0}),
    ("get_inventory_levels", {"product_ids": ["not-an-id"]}),
    ("compare_order_periods", {"comparison": "arbitrary"}),
    ("get_orders_summary", {"api_key": "forbidden"}),
])
def test_illegal_candidate_parameters_are_rejected(name, arguments):
    with pytest.raises(ValidationError):
        TOOL_SPEC_REGISTRY[name].validate_candidates(arguments)


@pytest.mark.asyncio
async def test_invalid_candidates_never_reach_tool(monkeypatch):
    called = []

    class Tool:
        async def ainvoke(self, arguments):
            called.append(arguments)

    monkeypatch.setitem(LOCAL_TOOL_REGISTRY, "get_order_list", Tool())
    plan = DispatchPlan(
        ("get_order_list",), False, "test",
        candidate_arguments={"get_order_list": {"limit": 9999}},
    )
    with pytest.raises(ValidationError):
        await read_only_tool_dispatcher.execute(
            plan, "订单", date_from="2026-09-01", date_to="2026-09-02", timezone="Asia/Shanghai",
        )
    assert called == []


def test_semantic_plan_accepts_structured_candidates_and_server_fields_are_forbidden():
    allowed = set(TOOL_SPEC_REGISTRY)
    plan = SemanticToolPlanner._validate({
        "route": "shopify",
        "tools": [],
        "tool_calls": [{"name": "get_order_list", "arguments": {"status": "open", "limit": 12}}],
        "requires_analysis": False,
    }, allowed, "test")
    assert plan is not None
    assert plan.tools == ("get_order_list",)
    assert plan.candidate_arguments["get_order_list"] == {"status": "open", "limit": 12}

    assert SemanticToolPlanner._validate({
        "route": "shopify",
        "tools": [],
        "tool_calls": [{"name": "get_order_list", "arguments": {"date_from": "2026-09-01"}}],
        "requires_analysis": False,
        "reason": "非法服务端参数",
        "message": "",
    }, allowed, "test") is None


@pytest.mark.asyncio
async def test_mcp_server_exposes_all_registered_tools_and_manifest():
    names = {tool.name for tool in await mcp.list_tools()}
    assert set(TOOL_SPEC_REGISTRY).issubset(names)
    assert {"health", "tool_manifest"}.issubset(names)


def test_parameter_evaluation_dataset_has_three_hundred_cases():
    path = Path(__file__).parents[1] / "fixtures/tool_parameter_cases.jsonl"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(cases) == 300
    assert len({row["id"] for row in cases}) == 300
    assert sum(not row["valid"] for row in cases) == 50
