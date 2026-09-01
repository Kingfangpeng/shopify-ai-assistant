"""时间工具"""

from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.tools import tool


@tool
def get_current_time(timezone: str = "America/New_York") -> str:
    """获取指定时区的当前时间

    Args:
        timezone: 时区名称，默认美东时间
    """
    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        return now.strftime(f"%Y-%m-%d %H:%M:%S {timezone}")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
