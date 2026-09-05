import httpx
import pytest

from app.integrations.shopify.client import (
    ShopifyGraphQLClient,
    ShopifyGraphQLError,
    ShopifyPermissionError,
    ShopifyRateLimitError,
)
from app.integrations.shopify.service import ShopifyService


@pytest.mark.asyncio
async def test_client_uses_fixed_2026_07_endpoint_and_rejects_ssrf():
    client = ShopifyGraphQLClient("king-store.myshopify.com", "shpat_real-test-token", "2026-07")
    assert client.endpoint == "https://king-store.myshopify.com/admin/api/2026-07/graphql.json"
    unsafe = ShopifyGraphQLClient("127.0.0.1", "shpat_real-test-token", "2026-07")
    assert not unsafe.configured


@pytest.mark.asyncio
async def test_graphql_access_denied_is_diagnostic():
    def handler(_request):
        return httpx.Response(200, json={"errors": [{"message": "read_orders required", "extensions": {"code": "ACCESS_DENIED"}}]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = ShopifyGraphQLClient("king-store.myshopify.com", "shpat_real-test-token", http_client=http_client)
        with pytest.raises(ShopifyPermissionError, match="read_orders"):
            await client.execute("query { shop { name } }")


@pytest.mark.asyncio
async def test_graphql_throttle_retries_three_times(monkeypatch):
    calls = 0
    def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={
            "errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}],
            "extensions": {"cost": {"requestedQueryCost": 20, "throttleStatus": {"currentlyAvailable": 0, "restoreRate": 50}}},
        })
    async def no_sleep(_seconds): return None
    monkeypatch.setattr("app.integrations.shopify.client.asyncio.sleep", no_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ShopifyGraphQLClient("king-store.myshopify.com", "shpat_real-test-token", http_client=http_client)
        with pytest.raises(ShopifyRateLimitError):
            await client.execute("query { shop { name } }")
    assert calls == 3


class PagedClient:
    configured = True
    def __init__(self): self.calls = 0
    async def execute(self, _query, variables=None):
        self.calls += 1
        if self.calls == 1:
            return {"orders": {"nodes": [{
                "cancelledAt": None,
                "currentTotalPriceSet": {"shopMoney": {"amount": "100", "currencyCode": "USD"}},
                "totalRefundedSet": {"shopMoney": {"amount": "10", "currencyCode": "USD"}},
            }], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}
        assert variables["after"] == "next"
        return {"orders": {"nodes": [{
            "cancelledAt": "2026-08-01T00:00:00Z",
            "currentTotalPriceSet": {"shopMoney": {"amount": "50", "currencyCode": "USD"}},
            "totalRefundedSet": {"shopMoney": {"amount": "0", "currencyCode": "USD"}},
        }], "pageInfo": {"hasNextPage": False, "endCursor": None}}}


class StatusClient:
    configured = True

    async def execute(self, _query, variables=None):
        return {
            "shop": {
                "name": "King Store",
                "myshopifyDomain": "king-store.myshopify.com",
                "currencyCode": "EUR",
                "ianaTimezone": "America/Los_Angeles",
                "timezoneOffset": "-0700",
                "timezoneOffsetMinutes": -420,
            },
            "currentAppInstallation": {"accessScopes": [{"handle": "read_orders"}]},
        }


class ShopifyQLClient:
    configured = True

    def __init__(self, payload):
        self.payload = payload
        self.statements = []

    async def execute(self, _query, variables=None):
        self.statements.append((variables or {}).get("query"))
        return {"shopifyqlQuery": self.payload}


@pytest.mark.asyncio
async def test_shop_status_exposes_store_timezone_for_date_resolution():
    result = await ShopifyService(StatusClient()).status()
    assert result["timezone"] == "America/Los_Angeles"
    assert result["timezone_offset_minutes"] == -420
    assert result["analytics_scope_granted"] is False


@pytest.mark.asyncio
async def test_shopifyql_traffic_overview_is_normalized_and_server_generated():
    client = ShopifyQLClient({
        "parseErrors": [],
        "tableData": {
            "columns": [{"name": "sessions", "dataType": "INTEGER", "displayName": "Sessions"}],
            "rows": [{
                "sessions": "9",
                "online_store_visitors": "8",
                "pageviews": "18",
                "pageviews_per_session": "2.0",
                "average_session_duration": "61.9",
                "bounces": "2",
                "bounce_rate": "0.2222",
                "sessions_with_cart_additions": "3",
                "sessions_that_reached_checkout": "2",
                "sessions_that_completed_checkout": "1",
                "conversion_rate": "0.1111",
            }],
        },
    })
    result = await ShopifyService(client).traffic_overview("2026-09-01", "2026-09-03")
    assert result["source"] == "shopify_analytics"
    assert result["sessions"] == 9
    assert result["bounce_rate_pct"] == 22.22
    assert result["conversion_rate_pct"] == 11.11
    assert "FROM sessions" in client.statements[0]
    assert "SINCE 2026-09-01 UNTIL 2026-09-03" in client.statements[0]


@pytest.mark.asyncio
async def test_shopifyql_parse_error_is_not_reported_as_empty_data():
    service = ShopifyService(ShopifyQLClient({
        "parseErrors": ["Column Not Found"],
        "tableData": None,
    }))
    with pytest.raises(ShopifyGraphQLError, match="Column Not Found"):
        await service.traffic_overview("2026-09-01", "2026-09-03")


@pytest.mark.asyncio
async def test_traffic_breakdown_rejects_arbitrary_shopifyql_dimension():
    service = ShopifyService(ShopifyQLClient({"parseErrors": [], "tableData": {"columns": [], "rows": []}}))
    with pytest.raises(ValueError, match="流量维度只支持"):
        await service.traffic_breakdown("2026-09-01", "2026-09-03", "orders DELETE")


@pytest.mark.asyncio
async def test_orders_summary_paginates_and_calculates_metrics():
    service = ShopifyService(PagedClient())
    result = await service.orders_summary("2026-08-01", "2026-08-31")
    assert result["total_orders"] == 2
    assert result["gmv"] == 150.0
    assert result["aov"] == 75.0
    assert result["cancel_rate_pct"] == 50.0
    assert result["refund_amount"] == 10.0
    assert result["source"] == "shopify_graphql"


@pytest.mark.asyncio
async def test_order_period_comparison_uses_two_non_overlapping_equal_periods(monkeypatch):
    service = ShopifyService(PagedClient())
    calls = []

    async def summary(date_from, date_to):
        calls.append((date_from, date_to))
        if date_from == "2026-09-01":
            return {"source": "shopify_graphql", "currency": "EUR", "total_orders": 10, "gmv": 9000, "aov": 900, "warnings": []}
        return {"source": "shopify_graphql", "currency": "EUR", "total_orders": 8, "gmv": 8000, "aov": 1000, "warnings": []}

    monkeypatch.setattr(service, "orders_summary", summary)
    result = await service.order_period_comparison("2026-09-01", "2026-09-03")
    assert set(calls) == {("2026-09-01", "2026-09-03"), ("2026-08-29", "2026-08-31")}
    assert result["changes"]["orders"] == 2
    assert result["changes"]["orders_pct"] == 25.0
    assert result["changes"]["gmv"] == 1000.0
    assert result["changes"]["gmv_pct"] == 12.5


@pytest.mark.asyncio
async def test_orders_over_sixty_days_warn_about_scope():
    service = ShopifyService(PagedClient())
    result = await service.orders_summary("2026-06-01", "2026-08-15")
    assert any("read_all_orders" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_demo_data_is_explicit(monkeypatch):
    from app.config import config
    monkeypatch.setattr(config, "shopify_demo_mode", True)
    service = ShopifyService(ShopifyGraphQLClient("", ""))
    result = await service.orders_summary("2026-08-01", "2026-08-07")
    assert result["source"] == "demo"
    assert "演示数据" in result["warnings"][0]
