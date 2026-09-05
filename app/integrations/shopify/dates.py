"""Shopify 店铺时区下的自然语言日期范围解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DATE_RE = re.compile(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)")
RECENT_DAYS_RE = re.compile(
    r"(?:最近|过去|近|last|past)\s*(\d{1,3}|[一二三四五六七八九十两]{1,3})\s*(?:天|日|days?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StoreDateRange:
    date_from: str
    date_to: str
    timezone: str
    label: str
    resolved_at: str


def resolve_store_date_range(
    question: str,
    timezone_name: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    now: datetime | None = None,
) -> StoreDateRange:
    """把相对日期转换为 Shopify 店铺日历日期，单次最多 90 天。"""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
        timezone_name = "UTC"

    local_now = now.astimezone(zone) if now is not None else datetime.now(zone)
    today = local_now.date()

    if date_from or date_to:
        start = _parse_date(date_from or date_to or "")
        end = _parse_date(date_to or date_from or "")
        label = "指定日期"
    else:
        explicit = [_parse_date(value) for value in DATE_RE.findall(question)]
        if len(explicit) >= 2:
            start, end = explicit[0], explicit[1]
            label = "指定日期"
        elif len(explicit) == 1:
            start = end = explicit[0]
            label = "指定日期"
        else:
            start, end, label = _relative_range(question, today)

    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    if (end - start).days > 90:
        raise ValueError("单次查询日期范围不能超过 90 天")

    return StoreDateRange(
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        timezone=timezone_name,
        label=label,
        resolved_at=local_now.isoformat(),
    )


def _relative_range(question: str, today: date) -> tuple[date, date, str]:
    normalized = question.lower()
    recent_match = RECENT_DAYS_RE.search(normalized)
    if recent_match:
        days = max(1, _parse_day_count(recent_match.group(1)))
        if days > 90:
            raise ValueError("单次查询日期范围不能超过 90 天")
        return today - timedelta(days=days - 1), today, f"最近 {days} 天"
    if "前天" in normalized:
        target = today - timedelta(days=2)
        return target, target, "前天"
    if "昨天" in normalized or "yesterday" in normalized:
        target = today - timedelta(days=1)
        return target, target, "昨天"
    if "上周" in normalized or "last week" in normalized:
        this_monday = today - timedelta(days=today.weekday())
        return this_monday - timedelta(days=7), this_monday - timedelta(days=1), "上周"
    if "本周" in normalized or "this week" in normalized:
        return today - timedelta(days=today.weekday()), today, "本周"
    if "上月" in normalized or "上个月" in normalized or "last month" in normalized:
        this_month = today.replace(day=1)
        previous_end = this_month - timedelta(days=1)
        return previous_end.replace(day=1), previous_end, "上月"
    if "本月" in normalized or "这个月" in normalized or "this month" in normalized:
        return today.replace(day=1), today, "本月"
    if "今天" in normalized or "今日" in normalized or "today" in normalized:
        return today, today, "今天"
    return today - timedelta(days=6), today, "最近 7 天"


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc


def _parse_day_count(value: str) -> int:
    if value.isdigit():
        return int(value)
    normalized = value.replace("两", "二")
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if normalized == "十":
        return 10
    if "十" in normalized:
        tens, ones = normalized.split("十", 1)
        return (digits.get(tens, 1) * 10) + digits.get(ones, 0)
    if normalized in digits:
        return digits[normalized]
    raise ValueError("无法识别相对日期天数")
