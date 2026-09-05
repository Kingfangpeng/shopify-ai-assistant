"""只读 Agent 工具调度器：先规划，再真实执行允许列表中的工具。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.shopify_tool import (
    compare_order_periods,
    get_abandoned_checkouts,
    get_customer_segments,
    get_discount_performance,
    get_device_traffic,
    get_inventory_levels,
    get_landing_page_performance,
    get_order_list,
    get_orders_summary,
    get_product_performance,
    get_refund_stats,
    get_search_performance,
    get_traffic_geography,
    get_traffic_overview,
    get_traffic_sources,
    get_traffic_timeseries,
    get_web_performance,
)
from app.tools.time_tool import get_current_time


SHOPIFY_TOOL_REGISTRY = {
    tool.name: tool
    for tool in (
        compare_order_periods,
        get_orders_summary,
        get_abandoned_checkouts,
        get_inventory_levels,
        get_product_performance,
        get_customer_segments,
        get_refund_stats,
        get_discount_performance,
        get_order_list,
        get_traffic_overview,
        get_traffic_timeseries,
        get_traffic_sources,
        get_landing_page_performance,
        get_device_traffic,
        get_traffic_geography,
        get_search_performance,
        get_web_performance,
    )
}
LOCAL_TOOL_REGISTRY = {
    **SHOPIFY_TOOL_REGISTRY,
    retrieve_knowledge.name: retrieve_knowledge,
    get_current_time.name: get_current_time,
}


@dataclass(frozen=True)
class DispatchPlan:
    tools: tuple[str, ...]
    requires_analysis: bool
    reason: str
    planner: str = "deterministic"
    route: str = "shopify"
    message: str = ""

    @property
    def uses_shopify(self) -> bool:
        return any(name in SHOPIFY_TOOL_REGISTRY for name in self.tools)


@dataclass(frozen=True)
class ToolExecution:
    name: str
    result: Any


class ReadOnlyToolDispatcher:
    """规则路由保证关键数据问题一定触发真实工具，不依赖模型自觉调用。"""

    _analysis_re = re.compile(r"为什么|原因|分析|建议|优化|策略|趋势|对比|诊断|怎么办|why|how|recommend", re.I)

    def plan_shopify(self, question: str) -> DispatchPlan:
        text = question.strip().lower()
        tools: list[str] = []

        order_terms = (
            r"订单|出单|成交|单量|订单量|订单数|成交单数|交易单数|gmv|销售额|营业额|营收|"
            r"销售收入|交易额|流水|客单价|几单|多少单|卖了多少|orders?|revenue|turnover"
        )
        comparison_terms = (
            r"对比|比较|环比|同比|较(?:上|前|去)|去年同期|上个\s*[一二三四五六七八九十两\d]+\s*(?:天|日)|"
            r"上一个|前一个|前一段|vs\.?|versus|compare"
        )
        detail_terms = r"明细|列表|订单号|哪几单|哪些订单|最新订单|order list|details?"
        if re.search(order_terms, text) or "get_orders_summary" in text or "compare_order_periods" in text:
            if re.search(comparison_terms, text) or "compare_order_periods" in text:
                tools.append("compare_order_periods")
            else:
                tools.append("get_orders_summary")
        if re.search(detail_terms, text) or "get_order_list" in text:
            tools.append("get_order_list")
        if re.search(r"弃购|弃单|未完成结账|abandon", text) or "get_abandoned_checkouts" in text:
            tools.append("get_abandoned_checkouts")
        if re.search(r"库存|缺货|低库存|安全库存|\bsku\b|inventory|stock", text) or "get_inventory_levels" in text:
            tools.append("get_inventory_levels")
        if re.search(r"热销|畅销|产品表现|商品表现|单品|销量排行|产品销量|product performance|best.?sell", text) or "get_product_performance" in text:
            tools.append("get_product_performance")
        if re.search(r"客户分层|新客|老客|复购|客户国家|顾客国家|customer segment|repeat rate", text) or "get_customer_segments" in text:
            tools.append("get_customer_segments")
        if re.search(r"退款|退货|refund", text) or "get_refund_stats" in text:
            tools.append("get_refund_stats")
        if re.search(r"折扣|优惠码|优惠券|discount|coupon", text) or "get_discount_performance" in text:
            tools.append("get_discount_performance")

        traffic_terms = (
            r"网站.*(?:访问|流量|访客|浏览)|访问量|访客数|浏览量|页面浏览|独立访客|"
            r"在线商店.*(?:会话|流量|访客)|\b(?:sessions?|pageviews?|visitors?|traffic)\b"
        )
        if re.search(traffic_terms, text) or "get_traffic_overview" in text:
            tools.append("get_traffic_overview")
        if re.search(r"流量趋势|访问趋势|访客趋势|浏览趋势|按天.*(?:流量|访问|访客)|traffic trend", text) or "get_traffic_timeseries" in text:
            tools.append("get_traffic_timeseries")
        if re.search(r"流量来源|访问来源|访客来源|引荐来源|推荐来源|来源渠道|referrer|traffic source", text) or "get_traffic_sources" in text:
            tools.append("get_traffic_sources")
        if re.search(r"落地页|着陆页|入口页|landing page", text) or "get_landing_page_performance" in text:
            tools.append("get_landing_page_performance")
        if re.search(r"访问设备|访客设备|设备流量|手机.*访问|移动端.*访问|device traffic", text) or "get_device_traffic" in text:
            tools.append("get_device_traffic")
        if re.search(r"访客国家|访客地区|流量国家|访问国家|流量地区|traffic geography", text) or "get_traffic_geography" in text:
            tools.append("get_traffic_geography")
        if re.search(r"站内搜索|搜索转化|搜索表现|搜索点击|search conversion|site search", text) or "get_search_performance" in text:
            tools.append("get_search_performance")
        if re.search(r"网站速度|网页速度|页面速度|核心网页指标|web vitals|\blcp\b|\binp\b|\bcls\b|\bfcp\b", text) or "get_web_performance" in text:
            tools.append("get_web_performance")

        if re.search(r"店铺情况|运营情况|经营情况|整体表现|经营概况|运营概况", text):
            tools.extend(("get_orders_summary", "get_product_performance", "get_inventory_levels"))
        if re.search(r"(?:今天|昨天|最近|本周|这周|本月|这个月)?.{0,4}(?:生意|业绩).{0,6}(?:怎么样|如何)", text):
            tools.append("get_orders_summary")

        # 专项查询已经能完整回答时，不额外调用订单汇总；明确要求两个维度时仍保留。
        if "get_orders_summary" in tools:
            combined_order_refund = bool(re.search(
                r"订单.{0,8}(?:和|与|及|以及|同时).{0,8}(?:退款|退货)|"
                r"(?:退款|退货).{0,8}(?:和|与|及|以及|同时).{0,8}订单",
                text,
            ))
            combined_order_discount = bool(re.search(
                r"订单.{0,8}(?:和|与|及|以及|同时).{0,8}(?:折扣|优惠)|"
                r"(?:折扣|优惠).{0,8}(?:和|与|及|以及|同时).{0,8}订单",
                text,
            ))
            detail_needs_summary = bool(re.search(r"汇总|总数|总量|单量|销售额|营业额|\bgmv\b|客单价", text))
            if "get_order_list" in tools and not detail_needs_summary:
                tools.remove("get_orders_summary")
            if "get_orders_summary" in tools and "get_refund_stats" in tools and not combined_order_refund:
                tools.remove("get_orders_summary")
            if "get_orders_summary" in tools and "get_discount_performance" in tools and not combined_order_discount:
                tools.remove("get_orders_summary")

        unique = tuple(dict.fromkeys(tools))[:4]
        requires_analysis = bool(self._analysis_re.search(text)) or len(unique) > 1
        if unique == ("get_traffic_overview",) and not re.search(
            r"为什么|原因|分析|建议|优化|策略|趋势|对比|诊断|怎么办|why|recommend",
            text,
            re.I,
        ):
            # “访问量如何”是指标查询，直接格式化真实数据，避免无必要地把报表交给模型改写。
            requires_analysis = False
        if unique == ("compare_order_periods",) and not re.search(
            r"为什么|原因|归因|建议|优化|策略|诊断|怎么办|why|recommend",
            text,
            re.I,
        ):
            # 周期对比由确定性工具计算，模型不参与数字和百分比推导。
            requires_analysis = False
        return DispatchPlan(
            tools=unique,
            requires_analysis=requires_analysis,
            reason="匹配 Shopify 运营数据意图" if unique else "未匹配 Shopify 数据意图",
        )

    def plan_all(self, question: str) -> DispatchPlan:
        shopify_plan = self.plan_shopify(question)
        if shopify_plan.tools:
            return shopify_plan
        text = question.strip().lower()
        if re.search(r"知识库|参考资料|文档|运营经验|retrieve_knowledge", text):
            return DispatchPlan(("retrieve_knowledge",), True, "匹配知识库意图")
        if re.search(r"当前时间|现在几点|店铺时间|get_current_time", text):
            return DispatchPlan(("get_current_time",), False, "匹配店铺时间意图")
        return DispatchPlan((), True, "没有确定性工具匹配")

    def plan_safe_fallback(self, question: str) -> DispatchPlan:
        """模型规划不可用时覆盖常见口语；仍只返回只读允许列表工具。"""
        text = question.strip().lower()
        mappings = (
            (
                r"哪些?.{0,8}(?:产品|商品|货).{0,8}(?:卖得最多|卖得最好|最好卖|跑得最好|表现最好)|"
                r"(?:产品|商品).{0,8}(?:销售|营收|销量).{0,6}(?:最高|最多|最好)",
                "get_product_performance",
            ),
            (r"(?:产品|商品|货).{0,8}(?:快卖完|不够卖|剩得少)", "get_inventory_levels"),
            (r"(?:来了多少人|多少人访问|网站人气|店铺流量)", "get_traffic_overview"),
            (r"(?:生意|业绩|经营).{0,8}(?:怎么样|如何|多少)", "get_orders_summary"),
        )
        tools = tuple(name for pattern, name in mappings if re.search(pattern, text))[:4]
        if not tools:
            return DispatchPlan((), True, "语义规划和安全回退均未匹配", "safe_fallback")
        return DispatchPlan(
            tools=tools,
            requires_analysis=bool(self._analysis_re.search(text)) or len(tools) > 1,
            reason="模型规划不可用，命中本地口语安全回退",
            planner="safe_fallback",
        )

    async def execute(
        self,
        plan: DispatchPlan,
        question: str,
        *,
        date_from: str,
        date_to: str,
        timezone: str,
    ) -> list[ToolExecution]:
        if len(plan.tools) > 4 or any(name not in LOCAL_TOOL_REGISTRY for name in plan.tools):
            raise RuntimeError("计划包含不允许执行的工具或超过调用上限")
        executions: list[ToolExecution] = []
        for name in plan.tools:
            tool = LOCAL_TOOL_REGISTRY.get(name)
            if tool is None:
                raise RuntimeError(f"工具不在只读允许列表中: {name}")
            arguments = self._arguments(name, question, date_from, date_to, timezone)
            logger.info("Agent 调用只读工具: {} args={}", name, self._safe_arguments(arguments))
            result = await tool.ainvoke(arguments)
            executions.append(ToolExecution(name=name, result=result))
            logger.info("Agent 工具调用完成: {}", name)
        return executions

    @staticmethod
    def _arguments(name: str, question: str, date_from: str, date_to: str, timezone: str) -> dict[str, Any]:
        if name in {
            "get_orders_summary",
            "get_abandoned_checkouts",
            "get_customer_segments",
            "get_refund_stats",
            "get_discount_performance",
            "get_traffic_overview",
            "get_traffic_timeseries",
            "get_search_performance",
            "get_web_performance",
        }:
            return {"date_from": date_from, "date_to": date_to}
        if name == "compare_order_periods":
            previous_period_hint = bool(re.search(
                r"环比|上个|上一个|前一个|前一段|前\s*[一二三四五六七八九十两\d]+\s*(?:天|日)",
                question,
                re.I,
            ))
            comparison = "previous_year" if re.search(r"同比|去年同期", question, re.I) and not previous_period_hint else "previous_period"
            return {"date_from": date_from, "date_to": date_to, "comparison": comparison}
        if name in {
            "get_traffic_sources",
            "get_landing_page_performance",
            "get_device_traffic",
            "get_traffic_geography",
        }:
            return {"date_from": date_from, "date_to": date_to, "limit": 20}
        if name == "get_product_performance":
            return {"date_from": date_from, "date_to": date_to, "top_n": 10}
        if name == "get_order_list":
            return {"date_from": date_from, "date_to": date_to, "status": "any", "limit": 20}
        if name == "get_inventory_levels":
            return {"product_ids": None}
        if name == "retrieve_knowledge":
            return {"query": question}
        if name == "get_current_time":
            return {"timezone": timezone}
        raise RuntimeError(f"工具参数映射不存在: {name}")

    @staticmethod
    def _safe_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in arguments.items() if key not in {"token", "api_key", "password"}}


read_only_tool_dispatcher = ReadOnlyToolDispatcher()
