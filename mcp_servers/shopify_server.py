"""回环地址上的 Shopify MCP Server，17 个工具复用统一 ToolSpec 实现。"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier

from app.agent.tool_registry import TOOL_SPEC_REGISTRY, tool_catalog_hash
from app.config import config


def _auth():  # type: ignore[no-untyped-def]
    if not config.mcp_service_token:
        return None
    return StaticTokenVerifier(tokens={
        config.mcp_service_token: {"client_id": "shopify-ai-service", "scopes": ["tools:read"]},
    }, required_scopes=["tools:read"])


mcp = FastMCP(
    "shopify-mcp-server",
    version="1.0.0",
    auth=_auth(),
    strict_input_validation=True,
    mask_error_details=True,
)


async def _invoke(name: str, arguments: dict[str, Any]):
    spec = TOOL_SPEC_REGISTRY[name]
    return await spec.implementation.ainvoke(spec.validate_execution(arguments))


@mcp.tool()
async def compare_order_periods(date_from: str, date_to: str, comparison: str = "previous_period") -> dict:
    """对比当前周期与上一等长周期或去年同期。"""
    return await _invoke("compare_order_periods", locals())


@mcp.tool()
async def get_orders_summary(date_from: str, date_to: str) -> dict:
    """查询订单量、GMV、AOV、取消率和退款金额。"""
    return await _invoke("get_orders_summary", locals())


@mcp.tool()
async def get_abandoned_checkouts(date_from: str, date_to: str) -> dict:
    """查询弃购数量、金额与恢复率。"""
    return await _invoke("get_abandoned_checkouts", locals())


@mcp.tool()
async def get_inventory_levels(product_ids: list[str] | None = None) -> list:
    """查询产品库存并标记低库存项目。"""
    return await _invoke("get_inventory_levels", locals())


@mcp.tool()
async def get_product_performance(date_from: str, date_to: str, top_n: int = 10) -> list:
    """查询产品销量、营收与退款表现。"""
    return await _invoke("get_product_performance", locals())


@mcp.tool()
async def get_customer_segments(date_from: str, date_to: str) -> dict:
    """查询新老客、复购率与国家分布。"""
    return await _invoke("get_customer_segments", locals())


@mcp.tool()
async def get_refund_stats(date_from: str, date_to: str) -> dict:
    """查询退款数量、金额和退款订单占比。"""
    return await _invoke("get_refund_stats", locals())


@mcp.tool()
async def get_discount_performance(date_from: str, date_to: str) -> list:
    """查询折扣码使用、归因销售额与 ROI。"""
    return await _invoke("get_discount_performance", locals())


@mcp.tool()
async def get_order_list(
    date_from: str,
    date_to: str,
    status: str = "any",
    limit: int = 20,
) -> list:
    """按状态查询订单列表。"""
    return await _invoke("get_order_list", locals())


@mcp.tool()
async def get_traffic_overview(date_from: str, date_to: str) -> dict:
    """查询访客、会话、浏览、转化率和漏斗。"""
    return await _invoke("get_traffic_overview", locals())


@mcp.tool()
async def get_traffic_timeseries(date_from: str, date_to: str) -> list:
    """查询按日流量和转化趋势。"""
    return await _invoke("get_traffic_timeseries", locals())


@mcp.tool()
async def get_traffic_sources(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询流量来源分布。"""
    return await _invoke("get_traffic_sources", locals())


@mcp.tool()
async def get_landing_page_performance(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询落地页访问与转化。"""
    return await _invoke("get_landing_page_performance", locals())


@mcp.tool()
async def get_device_traffic(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询桌面、手机和平板流量。"""
    return await _invoke("get_device_traffic", locals())


@mcp.tool()
async def get_traffic_geography(date_from: str, date_to: str, limit: int = 20) -> dict:
    """查询访客国家和地区分布。"""
    return await _invoke("get_traffic_geography", locals())


@mcp.tool()
async def get_search_performance(date_from: str, date_to: str) -> dict:
    """查询站内搜索点击、加购与成交漏斗。"""
    return await _invoke("get_search_performance", locals())


@mcp.tool()
async def get_web_performance(date_from: str, date_to: str) -> dict:
    """查询在线商店 Core Web Vitals。"""
    return await _invoke("get_web_performance", locals())


@mcp.tool()
def tool_manifest() -> dict:
    """返回 ToolSpec 版本与候选参数 Schema hash，用于一致性健康检查。"""
    tools = {
        name: {"version": spec.version, "schema_hash": spec.schema_hash}
        for name, spec in TOOL_SPEC_REGISTRY.items()
    }
    return {"tools": tools, "count": len(tools), "catalog_hash": tool_catalog_hash()}


@mcp.tool()
def health() -> dict:
    """返回 MCP 服务健康状态。"""
    return {"status": "ready", "tools": len(TOOL_SPEC_REGISTRY), "transport": "streamable-http"}


if __name__ == "__main__":
    if not config.mcp_service_token:
        raise RuntimeError("MCP_SERVICE_TOKEN 未配置，拒绝启动 MCP 服务")
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8003, path="/mcp")
