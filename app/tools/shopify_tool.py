"""Read-only LangChain tools backed by Shopify Admin GraphQL 2026-07."""

from typing import Optional

from langchain_core.tools import tool

from app.integrations.shopify.service import shopify_service


@tool
async def get_orders_summary(date_from: str, date_to: str) -> dict:
    """查询订单数、GMV、AOV、取消率和退款金额。日期格式为 YYYY-MM-DD。"""
    return await shopify_service.orders_summary(date_from, date_to)


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
