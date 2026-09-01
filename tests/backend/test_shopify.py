import httpx
import pytest

from app.integrations.shopify.client import ShopifyGraphQLClient, ShopifyPermissionError, ShopifyRateLimitError
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
