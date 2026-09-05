"""时间工具"""

from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.tools import tool

from app.integrations.shopify.service import shopify_service


@tool
async def get_current_time(timezone: str | None = None) -> str:
    """获取指定时区的当前时间；未指定时使用 Shopify 店铺时区。

    Args:
        timezone: 可选 IANA 时区名称
    """
    try:
        if not timezone:
            status = await shopify_service.status()
            timezone = str(status.get("timezone") or "UTC")
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        return now.strftime(f"%Y-%m-%d %H:%M:%S {timezone}")
    except Exception:
        return datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S UTC")
