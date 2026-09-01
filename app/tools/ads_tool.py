"""广告平台工具集 - Facebook Marketing API + Google Ads API

未配置 API 凭证时返回 mock 数据，方便开发测试。
"""

from langchain_core.tools import tool
from loguru import logger

from app.config import config


def _fb_ok() -> bool:
    return bool(config.facebook_access_token and config.facebook_ad_account_id)


def _google_ok() -> bool:
    return bool(config.google_ads_refresh_token and config.google_ads_customer_id)


@tool
def get_facebook_account_overview(date_from: str, date_to: str) -> dict:
    """查询 Facebook 广告账户整体表现（花费、ROAS、CPC、CTR、转化数）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"Facebook 账户概览: {date_from}~{date_to}")
    if not _fb_ok():
        return {
            "source": "mock", "platform": "facebook",
            "period": {"from": date_from, "to": date_to},
            "spend_usd": 3240.50, "revenue_usd": 5832.90, "roas": 1.8,
            "impressions": 284500, "clicks": 4267, "ctr_pct": 1.50,
            "cpc_usd": 0.76, "conversions": 87, "cpp_usd": 37.25,
            "note": "ROAS 1.8x 低于目标 3.0x，建议重点优化",
        }
    return {"message": "Configure Facebook API to get real data"}


@tool
def get_facebook_campaign_breakdown(date_from: str, date_to: str) -> list:
    """查询 Facebook 各 Campaign 花费、ROAS、CPA 明细

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"Facebook Campaign 分解: {date_from}~{date_to}")
    if not _fb_ok():
        return [
            {"name": "Prospecting - Lookalike 2%", "objective": "CONVERSIONS",
             "status": "ACTIVE", "spend_usd": 1200.0, "roas": 2.1, "cpa_usd": 28.50, "conversions": 42},
            {"name": "Retargeting - 7D Visitors", "objective": "CONVERSIONS",
             "status": "ACTIVE", "spend_usd": 680.0, "roas": 4.8, "cpa_usd": 18.20, "conversions": 37},
            {"name": "Top of Funnel - Broad", "objective": "REACH",
             "status": "ACTIVE", "spend_usd": 890.0, "roas": 0.8, "cpa_usd": 111.25, "conversions": 8},
        ]
    return [{"message": "Configure Facebook API to get real data"}]


@tool
def get_facebook_adset_performance(campaign_id: str, date_from: str, date_to: str) -> list:
    """查询 Facebook 指定 Campaign 下 AdSet 表现

    Args:
        campaign_id: Campaign ID
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"Facebook AdSet: campaign_id={campaign_id}")
    if not _fb_ok():
        return [
            {"name": "Lookalike 2% - US Women 25-44", "audience_size": 2400000,
             "frequency": 1.8, "spend_usd": 620.0, "roas": 2.4},
            {"name": "Interest - Tech Enthusiasts", "audience_size": 5800000,
             "frequency": 1.2, "spend_usd": 380.0, "roas": 1.6},
        ]
    return [{"message": "Configure Facebook API to get real data"}]


@tool
def get_facebook_creative_stats(date_from: str, date_to: str, top_n: int = 5) -> list:
    """查询 Facebook 广告素材表现（CTR、Hook Rate、ROAS）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        top_n: 返回 Top N 素材
    """
    logger.info(f"Facebook 素材表现: top_n={top_n}")
    if not _fb_ok():
        return [
            {"name": "UGC Video - Unboxing", "format": "video",
             "spend_usd": 890.0, "ctr_pct": 2.8, "hook_rate_pct": 42.0, "roas": 3.4},
            {"name": "Product Demo 15s", "format": "video",
             "spend_usd": 650.0, "ctr_pct": 2.1, "hook_rate_pct": 35.0, "roas": 2.8},
            {"name": "Static Lifestyle", "format": "image",
             "spend_usd": 420.0, "ctr_pct": 1.4, "hook_rate_pct": None, "roas": 1.9},
        ][:top_n]
    return [{"message": "Configure Facebook API to get real data"}]


@tool
def get_google_campaign_overview(date_from: str, date_to: str) -> dict:
    """查询 Google Ads 账户整体表现（花费、ROAS、CPC、CTR）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"Google 账户概览: {date_from}~{date_to}")
    if not _google_ok():
        return {
            "source": "mock", "platform": "google",
            "period": {"from": date_from, "to": date_to},
            "cost_usd": 1890.20, "revenue_usd": 7561.0, "roas": 4.0,
            "impressions": 142000, "clicks": 3124, "ctr_pct": 2.20,
            "cpc_usd": 0.61, "conversions": 94, "avg_cpa_usd": 20.11,
        }
    return {"message": "Configure Google Ads API to get real data"}


@tool
def get_google_keyword_performance(date_from: str, date_to: str, top_n: int = 20) -> list:
    """查询 Google Ads 关键词表现（展示、点击、花费、转化、ROAS）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        top_n: 返回 Top N 关键词
    """
    logger.info(f"Google 关键词表现: top_n={top_n}")
    if not _google_ok():
        return [
            {"keyword": "wireless earbuds", "match_type": "EXACT",
             "impressions": 18400, "clicks": 552, "cost_usd": 220.80,
             "conversions": 28, "roas": 6.4},
            {"keyword": "best bluetooth earbuds", "match_type": "PHRASE",
             "impressions": 12300, "clicks": 369, "cost_usd": 184.50,
             "conversions": 19, "roas": 5.1},
            {"keyword": "wireless headphones", "match_type": "BROAD",
             "impressions": 45000, "clicks": 675, "cost_usd": 270.0,
             "conversions": 12, "roas": 2.2},
        ][:top_n]
    return [{"message": "Configure Google Ads API to get real data"}]


@tool
def get_roas_trend(platform: str, date_from: str, date_to: str, granularity: str = "day") -> list:
    """查询 ROAS 时间序列趋势

    Args:
        platform: facebook / google / all
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        granularity: day / week
    """
    logger.info(f"ROAS 趋势: platform={platform}, {date_from}~{date_to}")
    from datetime import datetime, timedelta
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    trend = []
    current = start
    idx = 0
    while current <= end:
        roas_base = round(max(1.5, 3.5 - idx * 0.2), 1)
        if platform in ("facebook", "all"):
            trend.append({"date": current.strftime("%Y-%m-%d"), "platform": "facebook",
                         "roas": round(roas_base * 0.7, 1), "spend_usd": round(450 + idx * 10, 2)})
        if platform in ("google", "all"):
            trend.append({"date": current.strftime("%Y-%m-%d"), "platform": "google",
                         "roas": round(roas_base * 1.4, 1), "spend_usd": round(270 + idx * 5, 2)})
        current += timedelta(days=1)
        idx += 1
    return trend


@tool
def compare_platform_performance(date_from: str, date_to: str) -> dict:
    """对比 Facebook vs Google 广告核心指标

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    logger.info(f"平台对比: {date_from}~{date_to}")
    return {
        "period": {"from": date_from, "to": date_to},
        "facebook": {"spend_usd": 3240.50, "roas": 1.8, "cpc_usd": 0.76,
                     "ctr_pct": 1.50, "conversions": 87, "cpp_usd": 37.25},
        "google": {"spend_usd": 1890.20, "roas": 4.0, "cpc_usd": 0.61,
                   "ctr_pct": 2.20, "conversions": 94, "cpp_usd": 20.11},
        "insights": [
            "Google ROAS (4.0x) 显著高于 Facebook (1.8x)",
            "Facebook 花费占比 63%，但转化占比仅 48%",
            "建议将部分 Facebook 预算转移至 Google",
        ]
    }
