"""工具模块 - 供 Agent 调用的各种工具"""

from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time
from app.tools.shopify_tool import (
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
DEFAULT_LOCAL_AGENT_TOOLS = (
    retrieve_knowledge,
    get_current_time,
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

__all__ = [
    "DEFAULT_LOCAL_AGENT_TOOLS",
    "retrieve_knowledge",
    "get_current_time",
]
