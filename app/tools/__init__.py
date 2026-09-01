"""工具模块 - 供 Agent 调用的各种工具"""

from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time
from app.tools.shopify_tool import (
    get_orders_summary,
    get_abandoned_checkouts,
    get_inventory_levels,
    get_product_performance,
    get_customer_segments,
    get_refund_stats,
    get_discount_performance,
    get_order_list,
)
DEFAULT_LOCAL_AGENT_TOOLS = (
    retrieve_knowledge,
    get_current_time,
    get_orders_summary,
    get_abandoned_checkouts,
    get_inventory_levels,
    get_product_performance,
    get_customer_segments,
    get_refund_stats,
    get_discount_performance,
    get_order_list,
)

__all__ = [
    "DEFAULT_LOCAL_AGENT_TOOLS",
    "retrieve_knowledge",
    "get_current_time",
]
