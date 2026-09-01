"""数据快照接口 - 直接返回核心指标，不走 Agent"""

from fastapi import APIRouter, Query
from loguru import logger

router = APIRouter(prefix="/snapshot")


@router.get("/shopify")
async def shopify_snapshot(days: int = Query(default=7, ge=1, le=90, description="查询天数")):
    """
    Shopify 核心指标快照（轻量接口，不走 Agent）

    返回最近 N 天的销售核心数据，适合 Dashboard 展示。
    未配置 Shopify API 时返回 mock 数据。
    """
    try:
        from app.tools.shopify_tool import get_orders_summary, get_abandoned_checkouts, get_inventory_levels
        from datetime import datetime, timedelta

        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # 获取订单汇总
        orders_data = get_orders_summary.invoke({"date_from": date_from, "date_to": date_to})
        # 获取弃购数据
        abandoned_data = get_abandoned_checkouts.invoke({"date_from": date_from, "date_to": date_to})
        # 获取低库存预警
        inventory_data = get_inventory_levels.invoke({})

        # 统计低库存产品数
        low_stock_count = sum(
            1 for item in (inventory_data if isinstance(inventory_data, list) else [])
            if item.get("low_stock", False)
        )

        return {
            "code": 200,
            "message": "success",
            "data": {
                "period": {"date_from": date_from, "date_to": date_to, "days": days},
                "orders": orders_data,
                "abandoned_checkouts": abandoned_data,
                "inventory_alerts": low_stock_count,
            }
        }
    except Exception as e:
        logger.error(f"Shopify 快照接口错误: {e}")
        return {
            "code": 500,
            "message": f"获取快照失败: {str(e)}",
            "data": None
        }


@router.get("/ads")
async def ads_snapshot(
    days: int = Query(default=7, ge=1, le=90, description="查询天数"),
    platform: str = Query(default="all", description="广告平台: facebook / google / all")
):
    """
    广告核心指标快照（轻量接口，不走 Agent）

    返回最近 N 天的广告投放核心数据。
    未配置广告 API 时返回 mock 数据。
    """
    try:
        from app.tools.ads_tool import get_roas_trend, compare_platform_performance
        from datetime import datetime, timedelta

        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        result = {}

        if platform in ("all", "facebook", "google"):
            # 获取 ROAS 趋势
            roas_trend = get_roas_trend.invoke({
                "platform": platform,
                "date_from": date_from,
                "date_to": date_to,
                "granularity": "day"
            })
            result["roas_trend"] = roas_trend

        if platform == "all":
            # 跨平台对比
            comparison = compare_platform_performance.invoke({
                "date_from": date_from,
                "date_to": date_to
            })
            result["platform_comparison"] = comparison

        return {
            "code": 200,
            "message": "success",
            "data": {
                "period": {"date_from": date_from, "date_to": date_to, "days": days},
                "platform": platform,
                **result,
            }
        }
    except Exception as e:
        logger.error(f"广告快照接口错误: {e}")
        return {
            "code": 500,
            "message": f"获取快照失败: {str(e)}",
            "data": None
        }
