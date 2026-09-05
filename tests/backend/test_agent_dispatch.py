from datetime import datetime, timezone

import pytest

from app.agent.dispatcher import (
    DispatchPlan,
    LOCAL_TOOL_REGISTRY,
    ToolExecution,
    read_only_tool_dispatcher,
)
from app.agent.ops.executor import executor
from app.agent.semantic_planner import SemanticToolPlan, SemanticToolPlanner, semantic_tool_planner
from app.core.llm_factory import llm_factory
from app.integrations.shopify.dates import StoreDateRange, resolve_store_date_range
from app.integrations.shopify.service import shopify_service
from app.services.chat.agent_service import chat_agent_service
from app.tools.shopify_tool import get_product_performance


@pytest.fixture(autouse=True)
def stub_planner_for_dispatch_integration(monkeypatch):
    """本模块后半部分测试格式化与工具执行，语义理解由独立实测和规划器测试验证。"""
    async def plan(question, *_args, **_kwargs):
        legacy = read_only_tool_dispatcher.plan_shopify(question)
        return SemanticToolPlan(
            legacy.tools, legacy.requires_analysis, "测试替身",
            "semantic_tool_call", "shopify" if legacy.tools else "knowledge",
        )
    monkeypatch.setattr(semantic_tool_planner, "plan", plan)


def test_today_uses_shopify_store_timezone_across_date_boundary():
    period = resolve_store_date_range(
        "今天出了几单",
        "America/Los_Angeles",
        now=datetime(2026, 9, 2, 0, 30, tzinfo=timezone.utc),
    )
    assert period.date_from == "2026-09-01"
    assert period.date_to == "2026-09-01"
    assert period.timezone == "America/Los_Angeles"


def test_recent_days_are_inclusive_and_limited_to_store_calendar():
    period = resolve_store_date_range(
        "最近 7 天订单情况",
        "Europe/Paris",
        now=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
    )
    assert period.date_from == "2026-08-27"
    assert period.date_to == "2026-09-02"


def test_chinese_recent_days_are_parsed_in_store_calendar():
    period = resolve_store_date_range(
        "最近三天单量营业额",
        "America/Los_Angeles",
        now=datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc),
    )
    assert period.date_from == "2026-09-01"
    assert period.date_to == "2026-09-03"
    assert period.label == "最近 3 天"


def test_relative_range_over_ninety_days_is_rejected():
    with pytest.raises(ValueError, match="90 天"):
        resolve_store_date_range(
            "最近 120 天订单情况",
            "UTC",
            now=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
        )


def test_order_question_routes_to_real_read_only_tool():
    plan = read_only_tool_dispatcher.plan_shopify("今天出了几单")
    assert plan.tools == ("get_orders_summary",)
    assert plan.uses_shopify is True
    assert plan.requires_analysis is False


def test_colloquial_business_question_routes_to_order_summary():
    plan = read_only_tool_dispatcher.plan_shopify("今天生意怎么样？")
    assert plan.tools == ("get_orders_summary",)


def test_plain_traffic_metric_question_does_not_need_model_rewrite():
    plan = read_only_tool_dispatcher.plan_shopify("今天网站的访问量如何")
    assert plan.tools == ("get_traffic_overview",)
    assert plan.requires_analysis is False


def test_order_comparison_words_route_to_deterministic_comparison_tool():
    question = "最近三天单量营业额对比上个三天是什么样的"
    plan = read_only_tool_dispatcher.plan_shopify(question)
    assert plan.tools == ("compare_order_periods",)
    assert plan.requires_analysis is False
    arguments = read_only_tool_dispatcher._arguments(
        "compare_order_periods",
        question,
        "2026-09-01",
        "2026-09-03",
        "America/Los_Angeles",
    )
    assert arguments["comparison"] == "previous_period"


def test_true_year_over_year_comparison_is_distinguished():
    arguments = read_only_tool_dispatcher._arguments(
        "compare_order_periods",
        "本月营业额同比去年同期",
        "2026-09-01",
        "2026-09-03",
        "America/Los_Angeles",
    )
    assert arguments["comparison"] == "previous_year"


@pytest.mark.asyncio
async def test_semantic_planner_accepts_valid_native_plan(monkeypatch):
    class Response:
        content = ""
        tool_calls = [
            {"name": "submit_read_only_plan", "args": {
                "route": "shopify", "tools": ["get_product_performance"],
                "requires_analysis": False, "reason": "销量排行", "message": "",
            }, "id": "good"},
        ]

    class FakeClient:
        def bind_tools(self, _tools, tool_choice="auto"):
            assert tool_choice == "auto"
            return self

        async def ainvoke(self, _messages):
            return Response()

    monkeypatch.setattr(llm_factory, "create_chat_model", lambda **_kwargs: FakeClient())
    plan = await SemanticToolPlanner().plan(
        "哪些产品卖得最多",
        "local-model",
        [get_product_performance],
    )
    assert plan is not None
    assert plan.tools == ("get_product_performance",)
    assert plan.planner == "semantic_tool_call"


@pytest.mark.asyncio
async def test_semantic_planner_falls_back_to_strict_json_for_models_without_tool_calls(monkeypatch):
    class Response:
        content = '{"route":"shopify","tools":["get_product_performance"],"requires_analysis":false,"reason":"产品销量排行","message":""}'
        tool_calls = []

    class FakeClient:
        def bind_tools(self, _tools, tool_choice="auto"):
            raise NotImplementedError("local model has no native tools")

        async def ainvoke(self, _messages):
            return Response()

    monkeypatch.setattr(llm_factory, "create_chat_model", lambda **_kwargs: FakeClient())
    plan = await SemanticToolPlanner().plan(
        "哪些产品卖得最多",
        "local-model",
        [get_product_performance],
    )
    assert plan is not None
    assert plan.tools == ("get_product_performance",)
    assert plan.planner == "semantic_json"


@pytest.mark.parametrize(
    ("question", "expected_tool"),
    [
        ("查看今天订单明细", "get_order_list"),
        ("最近七天弃购情况", "get_abandoned_checkouts"),
        ("哪些 SKU 低库存", "get_inventory_levels"),
        ("本月热销产品", "get_product_performance"),
        ("本月新老客和复购", "get_customer_segments"),
        ("昨天退款多少", "get_refund_stats"),
        ("优惠码表现如何", "get_discount_performance"),
        ("今天网站访问量", "get_traffic_overview"),
        ("最近七天流量趋势", "get_traffic_timeseries"),
        ("本月访客来源", "get_traffic_sources"),
        ("哪些落地页流量最高", "get_landing_page_performance"),
        ("移动端访问表现", "get_device_traffic"),
        ("访客国家分布", "get_traffic_geography"),
        ("站内搜索转化", "get_search_performance"),
        ("网站 LCP 表现", "get_web_performance"),
    ],
)
def test_all_shopify_intents_route_only_to_allowlisted_tools(question, expected_tool):
    plan = read_only_tool_dispatcher.plan_shopify(question)
    assert expected_tool in plan.tools
    assert set(plan.tools).issubset(LOCAL_TOOL_REGISTRY)
    assert all("create" not in name and "update" not in name and "delete" not in name for name in plan.tools)


@pytest.mark.asyncio
async def test_dispatcher_invokes_tool_with_resolved_dates(monkeypatch):
    calls = []

    class FakeTool:
        async def ainvoke(self, arguments):
            calls.append(arguments)
            return {"source": "shopify_graphql", "total_orders": 6}

    monkeypatch.setitem(LOCAL_TOOL_REGISTRY, "get_orders_summary", FakeTool())
    executions = await read_only_tool_dispatcher.execute(
        DispatchPlan(("get_orders_summary",), False, "test"),
        "今天出了几单",
        date_from="2026-09-01",
        date_to="2026-09-01",
        timezone="America/Los_Angeles",
    )
    assert calls == [{"date_from": "2026-09-01", "date_to": "2026-09-01"}]
    assert executions[0].result["total_orders"] == 6


@pytest.mark.asyncio
async def test_chat_agent_formats_simple_metric_after_mocked_semantic_plan(monkeypatch):
    async def resolve_period(_question):
        return StoreDateRange(
            "2026-09-01",
            "2026-09-01",
            "America/Los_Angeles",
            "今天",
            "2026-09-01T17:00:00-07:00",
        )

    async def execute(*_args, **_kwargs):
        return [ToolExecution("get_orders_summary", {
            "source": "shopify_graphql",
            "currency": "EUR",
            "total_orders": 6,
            "gmv": 6314.9,
            "aov": 1052.48,
            "cancelled_orders": 0,
            "cancel_rate_pct": 0,
            "refund_amount": 0,
        })]

    monkeypatch.setattr(shopify_service, "resolve_date_range", resolve_period)
    monkeypatch.setattr(read_only_tool_dispatcher, "execute", execute)
    result = await chat_agent_service.query("今天出了几单", [], "unused-model")
    assert result.source == "shopify_graphql"
    assert result.tools == ("get_orders_summary",)
    assert "6 单" in result.answer
    assert "€6,314.90" in result.answer
    assert result.timezone == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_chat_agent_semantically_selects_product_tool_for_natural_question(monkeypatch):
    async def semantic_plan(*_args, **_kwargs):
        return SemanticToolPlan(
            ("get_product_performance",),
            False,
            "识别为产品销量排行",
            "semantic_tool_call",
        )

    async def resolve_period(_question):
        return StoreDateRange(
            "2026-08-28", "2026-09-03", "America/Los_Angeles", "最近 7 天", "2026-09-03T12:00:00-07:00"
        )

    async def execute(plan, *_args, **_kwargs):
        assert plan.tools == ("get_product_performance",)
        assert plan.planner == "semantic_tool_call"
        return [ToolExecution("get_product_performance", [{
            "source": "shopify_graphql",
            "title": "Ark 2000",
            "units_sold": 42,
            "revenue": 8400,
            "currency": "EUR",
        }])]

    monkeypatch.setattr(semantic_tool_planner, "plan", semantic_plan)
    monkeypatch.setattr(shopify_service, "resolve_date_range", resolve_period)
    monkeypatch.setattr(read_only_tool_dispatcher, "execute", execute)
    result = await chat_agent_service.query("哪些产品卖得最多", [], "local-model")
    assert result.tools == ("get_product_performance",)
    assert result.planner == "semantic_tool_call"
    assert "Ark 2000" in result.answer
    assert "销量 42" in result.answer


@pytest.mark.asyncio
async def test_chat_stream_emits_real_tool_trace_and_metadata(monkeypatch):
    async def resolve_period(_question):
        return StoreDateRange(
            "2026-09-01",
            "2026-09-01",
            "America/Los_Angeles",
            "今天",
            "2026-09-01T17:00:00-07:00",
        )

    async def execute(*_args, **_kwargs):
        return [ToolExecution("get_orders_summary", {
            "source": "shopify_graphql",
            "currency": "EUR",
            "total_orders": 6,
            "gmv": 6314.9,
            "aov": 1052.48,
            "cancelled_orders": 0,
            "cancel_rate_pct": 0,
            "refund_amount": 0,
        })]

    monkeypatch.setattr(shopify_service, "resolve_date_range", resolve_period)
    monkeypatch.setattr(read_only_tool_dispatcher, "execute", execute)
    events = [
        event
        async for event in chat_agent_service.query_stream(
            "今天出了几单",
            [],
            "unused-model",
        )
    ]
    tool_events = [event["data"] for event in events if event["type"] == "tool"]
    assert tool_events == [
        {"name": "get_orders_summary", "status": "running", "message": "正在调用 get_orders_summary"},
        {"name": "get_orders_summary", "status": "complete", "message": "get_orders_summary 调用完成"},
    ]
    complete = next(event["data"] for event in events if event["type"] == "complete")
    assert complete["source"] == "shopify_graphql"
    assert complete["tools"] == ["get_orders_summary"]
    assert complete["timezone"] == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_order_period_comparison_is_formatted_without_model(monkeypatch):
    async def resolve_period(_question):
        return StoreDateRange(
            "2026-09-01", "2026-09-03", "America/Los_Angeles", "最近 3 天", "2026-09-03T12:00:00-07:00"
        )

    async def execute(*_args, **_kwargs):
        return [ToolExecution("compare_order_periods", {
            "source": "shopify_graphql",
            "comparison_label": "上一个等长周期",
            "currency": "EUR",
            "current": {"period": {"from": "2026-09-01", "to": "2026-09-03"}, "total_orders": 10, "gmv": 9000, "aov": 900},
            "previous": {"period": {"from": "2026-08-29", "to": "2026-08-31"}, "total_orders": 8, "gmv": 8000, "aov": 1000},
            "changes": {"orders": 2, "orders_pct": 25, "gmv": 1000, "gmv_pct": 12.5, "aov": -100, "aov_pct": -10},
        })]

    monkeypatch.setattr(shopify_service, "resolve_date_range", resolve_period)
    monkeypatch.setattr(read_only_tool_dispatcher, "execute", execute)
    result = await chat_agent_service.query("最近三天单量营业额对比上个三天", [], "unused-model")
    assert result.tools == ("compare_order_periods",)
    assert "2026-09-01 至 2026-09-03" in result.answer
    assert "10 单" in result.answer
    assert "+25.00%" in result.answer
    assert "€9,000.00" in result.answer


@pytest.mark.asyncio
async def test_ops_executor_uses_deterministic_dispatch_before_model(monkeypatch):
    calls = []

    async def execute_tools(plan, question, **kwargs):
        calls.append((plan.tools, question, kwargs))
        return [ToolExecution("get_orders_summary", {"total_orders": 6, "currency": "EUR"})]

    monkeypatch.setattr(read_only_tool_dispatcher, "execute", execute_tools)
    result = await executor({
        "input": "今天出了几单",
        "plan": ["查询今天订单数量和销售额"],
        "past_steps": [],
        "response": "",
        "context": {
            "date_from": "2026-09-01",
            "date_to": "2026-09-01",
            "timezone": "America/Los_Angeles",
        },
        "replan_count": 0,
    })
    assert calls[0][0] == ("get_orders_summary",)
    assert calls[0][2]["date_from"] == "2026-09-01"
    assert '"total_orders": 6' in result["past_steps"][0][1]
    assert result["plan"] == []


@pytest.mark.asyncio
async def test_traffic_question_calls_shopify_analytics_tool(monkeypatch):
    async def resolve_period(_question):
        return StoreDateRange(
            "2026-09-03", "2026-09-03", "America/Los_Angeles", "今天", "2026-09-03T12:00:00-07:00"
        )

    async def execute(plan, *_args, **_kwargs):
        assert plan.tools == ("get_traffic_overview",)
        return [ToolExecution("get_traffic_overview", {
            "source": "shopify_analytics",
            "sessions": 9,
            "online_store_visitors": 9,
            "pageviews": 18,
            "pageviews_per_session": 2,
            "average_session_duration_seconds": 75,
            "bounces": 3,
            "bounce_rate_pct": 33.33,
            "sessions_with_cart_additions": 2,
            "sessions_that_reached_checkout": 1,
            "sessions_that_completed_checkout": 1,
            "conversion_rate_pct": 11.11,
        })]

    monkeypatch.setattr(shopify_service, "resolve_date_range", resolve_period)
    monkeypatch.setattr(read_only_tool_dispatcher, "execute", execute)

    async def fallback_answer(_question, _history, _model, _plan, _executions, fallback):
        return fallback, False

    monkeypatch.setattr(chat_agent_service, "_answer", fallback_answer)
    events = [
        event
        async for event in chat_agent_service.query_stream(
            "今天网站的访问量如何",
            [],
            "unused-model",
        )
    ]
    answer = next(event["data"] for event in events if event["type"] == "content")
    complete = next(event["data"] for event in events if event["type"] == "complete")
    assert "9 次会话" in answer
    assert "9 位访客" in answer
    assert "18 次" in answer
    assert complete["source"] == "shopify_analytics"
    assert complete["tools"] == ["get_traffic_overview"]
