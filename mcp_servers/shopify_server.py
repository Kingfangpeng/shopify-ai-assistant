"""Shopify MCP Server - 提供 Shopify 数据查询工具

端口: 8003
Transport: streamable-http
"""

from fastmcp import FastMCP

mcp = FastMCP("shopify-mcp-server")


@mcp.tool()
async def get_orders_summary(date_from: str, date_to: str) -> dict:
    """查询指定日期范围内的订单汇总数据（GMV、AOV、取消率、退款金额）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.shopify_tool import get_orders_summary as _fn
    return await _fn.ainvoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
async def get_abandoned_checkouts(date_from: str, date_to: str) -> dict:
    """查询弃购数据（弃购数量、弃购金额、恢复率、高频弃购产品）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.shopify_tool import get_abandoned_checkouts as _fn
    return await _fn.ainvoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
async def get_inventory_levels() -> list:
    """查询所有产品库存水平，标记低库存产品（低于安全库存10件）"""
    from app.tools.shopify_tool import get_inventory_levels as _fn
    return await _fn.ainvoke({})


@mcp.tool()
async def get_product_performance(date_from: str, date_to: str, top_n: int = 10) -> list:
    """查询产品销售排行榜

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        top_n: 返回 Top N 产品，默认10
    """
    from app.tools.shopify_tool import get_product_performance as _fn
    return await _fn.ainvoke({"date_from": date_from, "date_to": date_to, "top_n": top_n})


@mcp.tool()
async def get_customer_segments(date_from: str, date_to: str) -> dict:
    """查询客户分层数据（新老客比例、复购率、国家分布）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.shopify_tool import get_customer_segments as _fn
    return await _fn.ainvoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
async def get_refund_stats(date_from: str, date_to: str) -> dict:
    """查询退款统计（退款率、退款原因分析）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.shopify_tool import get_refund_stats as _fn
    return await _fn.ainvoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
async def get_discount_performance(date_from: str, date_to: str) -> list:
    """查询优惠码效果（使用次数、带来的GMV、折扣金额、ROI）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.shopify_tool import get_discount_performance as _fn
    return await _fn.ainvoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
async def get_order_list(date_from: str, date_to: str, status: str = "any", limit: int = 50) -> list:
    """查询订单列表

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        status: 订单状态 any/open/closed/cancelled
        limit: 返回数量上限，默认50
    """
    from app.tools.shopify_tool import get_order_list as _fn
    return await _fn.ainvoke({"date_from": date_from, "date_to": date_to, "status": status, "limit": limit})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8003, path="/mcp")
