"""Read-only LangChain tools backed by Shopify Admin GraphQL 2026-07."""

from typing import Optional

from langchain_core.tools import tool

from app.integrations.shopify.service import shopify_service


@tool
async def get_orders_summary(date_from: str, date_to: str) -> dict:
    """查询订单数、GMV、AOV、取消率和退款金额。日期格式为 YYYY-MM-DD。"""
    return await shopify_service.orders_summary(date_from, date_to)


@tool
async def compare_order_periods(
    date_from: str,
    date_to: str,
    comparison: str = "previous_period",
) -> dict:
    """对比当前周期与上一个等长周期或去年同期的订单量、GMV 和客单价。"""
    return await shopify_service.order_period_comparison(date_from, date_to, comparison)


@tool
async def get_abandoned_checkouts(date_from: str, date_to: str) -> dict:
    """查询弃购数量、金额、恢复率和高频弃购产品。日期格式为 YYYY-MM-DD。"""
    return await shopify_service.abandoned_checkouts(date_from, date_to)


@tool
async def get_inventory_levels(product_ids: Optional[list[str]] = None) -> list:
    """查询 Shopify 商品变体库存并标记低库存项目。"""
    return await shopify_service.inventory_levels(product_ids)


@tool
async def get_product_performance(date_from: str, date_to: str, top_n: int = 10) -> list:
    """查询日期范围内的产品销量、营收和退款率排行。"""
    return await shopify_service.product_performance(date_from, date_to, top_n)


@tool
async def get_customer_segments(date_from: str, date_to: str) -> dict:
    """查询新老客、复购率和国家分布。"""
    return await shopify_service.customer_segments(date_from, date_to)


@tool
async def get_refund_stats(date_from: str, date_to: str) -> dict:
    """查询退款次数、金额和退款价值占比；不会推测 Shopify 未提供的原因。"""
    return await shopify_service.refund_stats(date_from, date_to)


@tool
async def get_discount_performance(date_from: str, date_to: str) -> list:
    """查询折扣码使用次数、归因销售额、折扣额和计算口径明确的 ROI。"""
    return await shopify_service.discount_performance(date_from, date_to)


@tool
async def get_order_list(date_from: str, date_to: str, status: str = "any", limit: int = 50) -> list:
    """查询订单列表，状态支持 any/open/closed/cancelled，最多返回 250 条。"""
    return await shopify_service.order_list(date_from, date_to, status, limit)


@tool
async def get_traffic_overview(date_from: str, date_to: str) -> dict:
    """查询在线商店访客、会话、浏览量、跳出率和加购到成交漏斗。"""
    return await shopify_service.traffic_overview(date_from, date_to)


@tool
async def get_traffic_timeseries(date_from: str, date_to: str) -> list:
    """查询按天统计的在线商店访客、会话、浏览量和转化率趋势。"""
    return await shopify_service.traffic_timeseries(date_from, date_to)


@tool
async def get_traffic_sources(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询在线商店流量来源及各来源的访问和转化表现。"""
    return await shopify_service.traffic_breakdown(date_from, date_to, "referrer_source", limit)


@tool
async def get_landing_page_performance(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询在线商店落地页的访问量和转化表现。"""
    return await shopify_service.traffic_breakdown(date_from, date_to, "landing_page_path", limit)


@tool
async def get_device_traffic(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询桌面、手机、平板等设备的访问和转化表现。"""
    return await shopify_service.traffic_breakdown(date_from, date_to, "session_device_type", limit)


@tool
async def get_traffic_geography(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询访客国家的访问和转化分布。"""
    return await shopify_service.traffic_breakdown(date_from, date_to, "session_country", limit)


@tool
async def get_search_performance(date_from: str, date_to: str) -> dict:
    """查询站内搜索会话、点击、加购和成交转化漏斗。"""
    return await shopify_service.search_performance(date_from, date_to)


@tool
async def get_web_performance(date_from: str, date_to: str) -> dict:
    """查询在线商店 Core Web Vitals：FCP、LCP、INP 和 CLS。"""
    return await shopify_service.web_performance(date_from, date_to)
