"""广告平台 MCP Server - 提供 Facebook / Google 广告数据查询工具

端口: 8004
Transport: streamable-http
"""

from fastmcp import FastMCP

mcp = FastMCP("ads-mcp-server")


@mcp.tool()
def get_facebook_account_overview(date_from: str, date_to: str) -> dict:
    """查询 Facebook 广告账户整体表现（花费、ROAS、CPC、CTR、转化数、CPP）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.ads_tool import get_facebook_account_overview as _fn
    return _fn.invoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
def get_facebook_campaign_breakdown(date_from: str, date_to: str) -> list:
    """查询 Facebook 各 Campaign 花费、ROAS、CPA 明细

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.ads_tool import get_facebook_campaign_breakdown as _fn
    return _fn.invoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
def get_facebook_adset_performance(campaign_id: str, date_from: str, date_to: str) -> list:
    """查询 Facebook 指定 Campaign 下的 AdSet 表现

    Args:
        campaign_id: Campaign ID
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.ads_tool import get_facebook_adset_performance as _fn
    return _fn.invoke({"campaign_id": campaign_id, "date_from": date_from, "date_to": date_to})


@mcp.tool()
def get_facebook_creative_stats(date_from: str, date_to: str, top_n: int = 5) -> list:
    """查询 Facebook 广告素材表现（CTR、Hook Rate、ROAS）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        top_n: 返回 Top N 素材，默认5
    """
    from app.tools.ads_tool import get_facebook_creative_stats as _fn
    return _fn.invoke({"date_from": date_from, "date_to": date_to, "top_n": top_n})


@mcp.tool()
def get_google_campaign_overview(date_from: str, date_to: str) -> dict:
    """查询 Google Ads 账户整体表现（花费、ROAS、CPC、CTR、转化数）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.ads_tool import get_google_campaign_overview as _fn
    return _fn.invoke({"date_from": date_from, "date_to": date_to})


@mcp.tool()
def get_google_keyword_performance(date_from: str, date_to: str, top_n: int = 20) -> list:
    """查询 Google Ads 关键词表现（展示、点击、花费、转化、ROAS）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        top_n: 返回 Top N 关键词，默认20
    """
    from app.tools.ads_tool import get_google_keyword_performance as _fn
    return _fn.invoke({"date_from": date_from, "date_to": date_to, "top_n": top_n})


@mcp.tool()
def get_roas_trend(platform: str, date_from: str, date_to: str, granularity: str = "day") -> list:
    """查询 ROAS 时间序列趋势

    Args:
        platform: 广告平台 facebook / google / all
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
        granularity: 粒度 day / week
    """
    from app.tools.ads_tool import get_roas_trend as _fn
    return _fn.invoke({"platform": platform, "date_from": date_from, "date_to": date_to, "granularity": granularity})


@mcp.tool()
def compare_platform_performance(date_from: str, date_to: str) -> dict:
    """对比 Facebook vs Google 广告核心指标（花费、ROAS、CPC、转化数）

    Args:
        date_from: 开始日期 YYYY-MM-DD
        date_to: 结束日期 YYYY-MM-DD
    """
    from app.tools.ads_tool import compare_platform_performance as _fn
    return _fn.invoke({"date_from": date_from, "date_to": date_to})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8004, path="/mcp")
