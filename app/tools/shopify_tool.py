"""Shopify Admin API 工具集

封装 Shopify Admin REST API，供 Executor Agent 调用。
未配置 SHOPIFY_ACCESS_TOKEN 时返回 mock 数据（方便开发测试）。
"""

from typing import Optional, List
from langchain_core.tools import tool
from loguru import logger

from app.config import config


def _is_shopify_configured() -> bool:
    token = (config.shopify_access_token or "").strip()
    domain = (config.shopify_store_domain or "").strip()
    return bool(
        token
        and domain
        and token not in {"shpat_your_token_here", "your-token"}
        and not token.startswith("shpat_your")
        and domain not in {"your-store.myshopify.com", "example.myshopify.com"}
    )


def _shopify_get(path: str, params: dict = None) -> dict:
    import httpx
    url = f"https://{config.shopify_store_domain}/admin/api/{config.shopify_api_version}{path}"
    headers = {"X-Shopify-Access-Token": config.shopify_access_token, "Content-Type": "application/json"}
    response = httpx.get(url, headers=headers, params=params or {}, timeout=30.0)
    response.raise_for_status()
    return response.json()


@tool
def get_orders_summary(date_from: str, date_to: str) -> dict:
    """查询订单汇总数据（GMV、AOV、取消率、退款金额）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"查询订单汇总: {date_from} ~ {date_to}")
    if not _is_shopify_configured():
        return {
            "source": "mock", "period": {"from": date_from, "to": date_to},
            "total_orders": 342, "gmv_usd": 18650.40, "aov_usd": 54.53,
            "cancelled_orders": 12, "cancel_rate_pct": 3.5,
            "refund_amount_usd": 890.20, "refund_rate_pct": 4.77,
        }
    try:
        data = _shopify_get("/orders.json", {
            "created_at_min": f"{date_from}T00:00:00",
            "created_at_max": f"{date_to}T23:59:59",
            "status": "any", "limit": 250,
            "fields": "id,total_price,financial_status,cancel_reason,refunds"
        })
        orders = data.get("orders", [])
        total = len(orders)
        gmv = sum(float(o.get("total_price", 0)) for o in orders)
        cancelled = sum(1 for o in orders if o.get("cancel_reason"))
        return {
            "source": "shopify_api", "period": {"from": date_from, "to": date_to},
            "total_orders": total, "gmv_usd": round(gmv, 2),
            "aov_usd": round(gmv / total, 2) if total > 0 else 0,
            "cancelled_orders": cancelled,
            "cancel_rate_pct": round(cancelled / total * 100, 2) if total > 0 else 0,
        }
    except Exception as e:
        logger.error(f"Shopify API 失败: {e}")
        return {"error": str(e)}


@tool
def get_abandoned_checkouts(date_from: str, date_to: str) -> dict:
    """查询弃购数据（弃购数量、金额、恢复率、高频弃购产品）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"查询弃购: {date_from} ~ {date_to}")
    if not _is_shopify_configured():
        return {
            "source": "mock", "period": {"from": date_from, "to": date_to},
            "total_abandoned": 89, "abandoned_value_usd": 4230.60,
            "recovered_count": 14, "recovery_rate_pct": 15.7,
            "avg_abandoned_value_usd": 47.54,
            "top_abandoned_products": [
                {"title": "Premium Wireless Earbuds", "count": 23},
                {"title": "Smart Watch Band", "count": 17},
            ],
        }
    try:
        data = _shopify_get("/checkouts.json", {
            "created_at_min": f"{date_from}T00:00:00",
            "created_at_max": f"{date_to}T23:59:59", "limit": 250
        })
        checkouts = data.get("checkouts", [])
        total = len(checkouts)
        total_value = sum(float(c.get("total_price", 0)) for c in checkouts)
        return {
            "source": "shopify_api", "period": {"from": date_from, "to": date_to},
            "total_abandoned": total, "abandoned_value_usd": round(total_value, 2),
            "avg_abandoned_value_usd": round(total_value / total, 2) if total > 0 else 0,
        }
    except Exception as e:
        logger.error(f"Shopify 弃购 API 失败: {e}")
        return {"error": str(e)}


@tool
def get_inventory_levels(product_ids: Optional[List[str]] = None) -> list:
    """查询库存水平，标记低库存产品（低于安全库存10件）

    Args:
        product_ids: 产品 ID 列表（可选，不传则查询全部）
    """
    logger.info(f"查询库存: product_ids={product_ids}")
    if not _is_shopify_configured():
        return [
            {"product_id": "1001", "title": "Wireless Earbuds - Black", "sku": "WE-BLK",
             "inventory_quantity": 5, "low_stock": True, "safety_stock": 10},
            {"product_id": "1001", "title": "Wireless Earbuds - White", "sku": "WE-WHT",
             "inventory_quantity": 23, "low_stock": False, "safety_stock": 10},
            {"product_id": "1002", "title": "Smart Watch Band S/M", "sku": "SWB-SM",
             "inventory_quantity": 3, "low_stock": True, "safety_stock": 10},
            {"product_id": "1003", "title": "Phone Case Bundle", "sku": "PCB-001",
             "inventory_quantity": 67, "low_stock": False, "safety_stock": 10},
        ]
    try:
        params = {"limit": 250}
        if product_ids:
            params["product_ids"] = ",".join(product_ids)
        data = _shopify_get("/variants.json", params)
        variants = data.get("variants", [])
        safety_stock = 10
        return [
            {"variant_id": str(v.get("id")), "title": v.get("title"), "sku": v.get("sku"),
             "inventory_quantity": v.get("inventory_quantity", 0),
             "low_stock": v.get("inventory_quantity", 0) < safety_stock,
             "safety_stock": safety_stock}
            for v in variants
        ]
    except Exception as e:
        logger.error(f"Shopify 库存 API 失败: {e}")
        return [{"error": str(e)}]


@tool
def get_product_performance(date_from: str, date_to: str, top_n: int = 10) -> list:
    """查询产品销售排行（销量、营收、退款率）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        top_n: 返回 Top N 产品
    """
    logger.info(f"查询产品表现: {date_from}~{date_to}")
    if not _is_shopify_configured():
        return [
            {"rank": 1, "title": "Premium Wireless Earbuds", "units_sold": 87,
             "revenue_usd": 4350.0, "return_rate_pct": 3.4},
            {"rank": 2, "title": "Phone Case Bundle", "units_sold": 63,
             "revenue_usd": 1890.0, "return_rate_pct": 1.6},
            {"rank": 3, "title": "Smart Watch Band", "units_sold": 45,
             "revenue_usd": 1350.0, "return_rate_pct": 5.6},
        ][:top_n]
    return [{"message": "Configure Shopify API to get real data"}]


@tool
def get_customer_segments(date_from: str, date_to: str) -> dict:
    """查询客户分层（新老客比例、复购率、国家分布）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"查询客户分层: {date_from}~{date_to}")
    if not _is_shopify_configured():
        return {
            "source": "mock", "new_customers": 198, "returning_customers": 144,
            "repeat_rate_pct": 42.1,
            "top_countries": [
                {"country": "United States", "orders": 187, "revenue_usd": 10230.0},
                {"country": "United Kingdom", "orders": 64, "revenue_usd": 3480.0},
                {"country": "Canada", "orders": 43, "revenue_usd": 2340.0},
            ]
        }
    return {"message": "Configure Shopify API to get real data"}


@tool
def get_refund_stats(date_from: str, date_to: str) -> dict:
    """查询退款统计（退款率、原因分析）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"查询退款: {date_from}~{date_to}")
    if not _is_shopify_configured():
        return {
            "source": "mock", "refund_count": 16, "refund_amount_usd": 890.20,
            "refund_rate_pct": 4.68,
            "top_reasons": [
                {"reason": "Product not as described", "count": 7, "pct": 43.8},
                {"reason": "Defective product", "count": 5, "pct": 31.2},
                {"reason": "Changed mind", "count": 4, "pct": 25.0},
            ]
        }
    return {"message": "Configure Shopify API to get real data"}


@tool
def get_discount_performance(date_from: str, date_to: str) -> list:
    """查询优惠码效果（使用次数、GMV贡献、ROI）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"查询折扣表现: {date_from}~{date_to}")
    if not _is_shopify_configured():
        return [
            {"code": "SAVE20", "usage_count": 47, "gmv_usd": 2820.0,
             "discount_amount_usd": 564.0, "roi": 5.0},
            {"code": "WELCOME10", "usage_count": 31, "gmv_usd": 1550.0,
             "discount_amount_usd": 155.0, "roi": 10.0},
        ]
    return [{"message": "Configure Shopify API to get real data"}]


@tool
def get_order_list(date_from: str, date_to: str, status: str = "any", limit: int = 50) -> list:
    """查询订单列表

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        status: 订单状态 any/open/closed/cancelled
        limit: 返回数量
    """
    logger.info(f"查询订单列表: {date_from}~{date_to}")
    if not _is_shopify_configured():
        return [
            {"order_id": "1001", "amount_usd": 59.99, "status": "paid", "country": "US"},
            {"order_id": "1002", "amount_usd": 129.00, "status": "paid", "country": "UK"},
        ]
    try:
        data = _shopify_get("/orders.json", {
            "created_at_min": f"{date_from}T00:00:00",
            "created_at_max": f"{date_to}T23:59:59",
            "status": status, "limit": min(limit, 250),
            "fields": "id,total_price,financial_status,billing_address,created_at"
        })
        orders = data.get("orders", [])
        return [
            {"order_id": str(o["id"]), "amount_usd": float(o.get("total_price", 0)),
             "status": o.get("financial_status"),
             "country": o.get("billing_address", {}).get("country_code", "N/A")}
            for o in orders
        ]
    except Exception as e:
        logger.error(f"Shopify 订单列表失败: {e}")
        return [{"error": str(e)}]
