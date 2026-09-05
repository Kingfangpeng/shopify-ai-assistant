"""数据快照接口 - 直接返回核心指标，不走 Agent"""

from fastapi import APIRouter, Query
from loguru import logger
from app.core.errors import AppError

router = APIRouter(prefix="/snapshot")


@router.get("/shopify")
async def shopify_snapshot(days: int = Query(default=7, ge=1, le=90, description="查询天数")):
    """
    Shopify 核心指标快照（轻量接口，不走 Agent）

    返回最近 N 天的销售核心数据，适合 Dashboard 展示。
    未配置 Shopify API 时返回明确配置错误；仅显式 Demo 模式返回演示数据。
    """
    try:
        from app.integrations.shopify.service import shopify_service

        period = await shopify_service.resolve_date_range(f"最近 {days} 天")
        date_from = period.date_from
        date_to = period.date_to

        # 获取订单汇总
        orders_data = await shopify_service.orders_summary(date_from, date_to)
        # 获取弃购数据
        abandoned_data = await shopify_service.abandoned_checkouts(date_from, date_to)
        # 获取低库存预警
        inventory_data = await shopify_service.inventory_levels()

        # 统计低库存产品数
        low_stock_count = sum(
            1 for item in (inventory_data if isinstance(inventory_data, list) else [])
            if item.get("low_stock", False)
        )

        return {
            "code": 200,
            "message": "success",
            "data": {
                "period": {
                    "date_from": date_from,
                    "date_to": date_to,
                    "days": days,
                    "timezone": period.timezone,
                },
                "orders": orders_data,
                "abandoned_checkouts": abandoned_data,
                "inventory_alerts": low_stock_count,
            }
        }
    except Exception as e:
        logger.exception("Shopify 快照接口错误")
        if isinstance(e, AppError):
            raise
        raise AppError("shopify_snapshot_failed", "Shopify 快照暂时不可用", 503) from e


@router.get("/ads")
async def ads_snapshot(
    days: int = Query(default=7, ge=1, le=90, description="查询天数"),
    platform: str = Query(default="all", description="广告平台: facebook / google / all")
):
    """广告能力本轮默认关闭。"""
    raise AppError("ads_disabled", "Facebook 和 Google Ads 本轮已关闭", 404)
