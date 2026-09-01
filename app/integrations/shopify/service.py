"""Shopify read-only business metrics built on Admin GraphQL 2026-07."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, AsyncIterator

from app.config import config
from .client import ShopifyGraphQLClient, ShopifyNotConfigured
from .queries import (
    ABANDONED_CHECKOUTS_QUERY,
    CUSTOMER_SEGMENTS_QUERY,
    DISCOUNTS_QUERY,
    INVENTORY_QUERY,
    ORDER_LIST_QUERY,
    ORDERS_SUMMARY_QUERY,
    PRODUCT_PERFORMANCE_QUERY,
    REFUNDS_QUERY,
    SHOP_STATUS_QUERY,
)


def _money(container: Any, field: str = "shopMoney") -> Decimal:
    try:
        value = (container or {}).get(field, {}).get("amount", "0")
        return Decimal(str(value))
    except (AttributeError, InvalidOperation):
        return Decimal("0")


def _money_set(node: dict[str, Any], key: str) -> Decimal:
    return _money(node.get(key))


def _round(value: Decimal | float, digits: int = 2) -> float:
    return round(float(value), digits)


class ShopifyService:
    max_records = 25_000

    def __init__(self, client: ShopifyGraphQLClient | None = None) -> None:
        self.client = client or ShopifyGraphQLClient()

    @property
    def configured(self) -> bool:
        return self.client.configured

    async def status(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "configured": False,
                "connected": False,
                "demo_mode": config.shopify_demo_mode,
                "api_version": config.shopify_api_version,
                "domain": None,
                "scopes": [],
            }
        data = await self.client.execute(SHOP_STATUS_QUERY)
        shop = data.get("shop") or {}
        scopes = [item.get("handle") for item in (data.get("currentAppInstallation") or {}).get("accessScopes", [])]
        return {
            "configured": True,
            "connected": True,
            "demo_mode": config.shopify_demo_mode,
            "api_version": config.shopify_api_version,
            "domain": shop.get("myshopifyDomain"),
            "shop_name": shop.get("name"),
            "currency": shop.get("currencyCode"),
            "scopes": sorted(scope for scope in scopes if scope),
        }

    def _period(self, date_from: str, date_to: str) -> tuple[date, date, str]:
        try:
            start = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
        except ValueError as exc:
            raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
        if end < start:
            raise ValueError("结束日期不能早于开始日期")
        if (end - start).days > 90:
            raise ValueError("单次查询日期范围不能超过 90 天")
        query = f"created_at:>={start.isoformat()} created_at:<={(end + timedelta(days=1)).isoformat()}"
        return start, end, query

    async def _nodes(
        self,
        document: str,
        connection: str,
        *,
        variables: dict[str, Any] | None = None,
        page_size: int = 100,
        limit: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        after: str | None = None
        seen = 0
        cap = min(limit or self.max_records, self.max_records)
        while seen < cap:
            page_vars = {**(variables or {}), "first": min(page_size, cap - seen), "after": after}
            data = await self.client.execute(document, page_vars)
            payload = data.get(connection) or {}
            nodes = payload.get("nodes") or []
            if not isinstance(nodes, list):
                return
            for node in nodes:
                if isinstance(node, dict):
                    yield node
                    seen += 1
                    if seen >= cap:
                        return
            page_info = payload.get("pageInfo") or {}
            if not page_info.get("hasNextPage") or not page_info.get("endCursor"):
                return
            after = str(page_info["endCursor"])

    def _source(self, *, partial: bool = False, warnings: list[str] | None = None) -> dict[str, Any]:
        combined = list(warnings or [])
        if partial:
            combined.append("结果达到 Shopify 25,000 条分页上限，已截断；请缩小筛选范围")
        return {
            "source": "shopify_graphql",
            "api_version": config.shopify_api_version,
            "is_partial": partial,
            "warnings": combined,
        }

    @staticmethod
    def _order_scope_warnings(start: date, end: date) -> list[str]:
        if (end - start).days > 60:
            return ["查询范围超过 60 天，Custom App 需要 read_all_orders 权限"]
        return []

    def _ensure_available(self, demo_factory) -> dict[str, Any] | list[dict[str, Any]] | None:
        if self.configured:
            return None
        if config.shopify_demo_mode:
            return demo_factory()
        raise ShopifyNotConfigured("Shopify 尚未连接；演示模式默认关闭")

    async def orders_summary(self, date_from: str, date_to: str) -> dict[str, Any]:
        demo = self._ensure_available(lambda: self._demo_orders(date_from, date_to))
        if demo is not None:
            return demo  # type: ignore[return-value]
        start, end, query = self._period(date_from, date_to)
        total = cancelled = 0
        gmv = refunds = Decimal("0")
        currency = "USD"
        async for order in self._nodes(ORDERS_SUMMARY_QUERY, "orders", variables={"query": query}):
            total += 1
            cancelled += int(bool(order.get("cancelledAt")))
            gmv += _money_set(order, "currentTotalPriceSet")
            refunds += _money_set(order, "totalRefundedSet")
            currency = ((order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}).get("currencyCode", currency)
        return {
            **self._source(partial=total >= self.max_records, warnings=self._order_scope_warnings(start, end)),
            "period": {"from": date_from, "to": date_to},
            "currency": currency,
            "total_orders": total,
            "gmv": _round(gmv),
            "aov": _round(gmv / total) if total else 0,
            "cancelled_orders": cancelled,
            "cancel_rate_pct": round(cancelled / total * 100, 2) if total else 0,
            "refund_amount": _round(refunds),
            "refund_rate_pct": round(float(refunds / gmv * 100), 2) if gmv else 0,
        }

    async def abandoned_checkouts(self, date_from: str, date_to: str) -> dict[str, Any]:
        demo = self._ensure_available(lambda: self._demo_abandoned(date_from, date_to))
        if demo is not None:
            return demo  # type: ignore[return-value]
        start, end, query = self._period(date_from, date_to)
        total = recovered = 0
        value = Decimal("0")
        products: Counter[str] = Counter()
        async for checkout in self._nodes(ABANDONED_CHECKOUTS_QUERY, "abandonedCheckouts", variables={"query": query}):
            total += 1
            recovered += int(bool(checkout.get("completedAt")))
            value += _money_set(checkout, "totalPriceSet")
            for item in (checkout.get("lineItems") or {}).get("nodes", []):
                products[str(item.get("title") or "未知商品")] += int(item.get("quantity") or 0)
        return {
            **self._source(partial=total >= self.max_records, warnings=self._order_scope_warnings(start, end)),
            "period": {"from": date_from, "to": date_to},
            "total_abandoned": total,
            "abandoned_value": _round(value),
            "recovered_count": recovered,
            "recovery_rate_pct": round(recovered / total * 100, 2) if total else 0,
            "avg_abandoned_value": _round(value / total) if total else 0,
            "top_abandoned_products": [
                {"title": title, "count": count} for title, count in products.most_common(10)
            ],
        }

    async def inventory_levels(self, product_ids: list[str] | None = None) -> list[dict[str, Any]]:
        demo = self._ensure_available(self._demo_inventory)
        if demo is not None:
            return demo  # type: ignore[return-value]
        requested = set(product_ids or [])
        result: list[dict[str, Any]] = []
        async for variant in self._nodes(INVENTORY_QUERY, "productVariants", page_size=100):
            product = variant.get("product") or {}
            product_id = str(product.get("id") or "")
            if requested and product_id not in requested:
                continue
            quantity = int(variant.get("inventoryQuantity") or 0)
            result.append({
                "source": "shopify_graphql",
                "api_version": config.shopify_api_version,
                "product_id": product_id,
                "variant_id": variant.get("id"),
                "title": f"{product.get('title', '')} · {variant.get('title', '')}".strip(" ·"),
                "sku": variant.get("sku"),
                "inventory_quantity": quantity,
                "low_stock": quantity < config.shopify_low_stock_threshold,
                "safety_stock": config.shopify_low_stock_threshold,
                "is_partial": False,
                "warnings": [],
            })
        if len(result) >= self.max_records:
            for item in result:
                item["is_partial"] = True
                item["warnings"] = ["结果达到 Shopify 25,000 条分页上限，已截断；请缩小筛选范围"]
        return result

    async def product_performance(self, date_from: str, date_to: str, top_n: int = 10) -> list[dict[str, Any]]:
        demo = self._ensure_available(self._demo_products)
        if demo is not None:
            return demo[: max(1, min(top_n, 50))]  # type: ignore[index]
        start, end, query = self._period(date_from, date_to)
        totals: dict[str, dict[str, Any]] = defaultdict(lambda: {"title": "", "units": 0, "revenue": Decimal("0"), "refunded": 0})
        order_count = 0
        async for order in self._nodes(PRODUCT_PERFORMANCE_QUERY, "orders", variables={"query": query}):
            order_count += 1
            for item in (order.get("lineItems") or {}).get("nodes", []):
                product = item.get("product") or {}
                product_id = str(product.get("id") or "unknown")
                totals[product_id]["title"] = product.get("title") or "未知商品"
                totals[product_id]["units"] += int(item.get("quantity") or 0)
                totals[product_id]["revenue"] += _money_set(item, "discountedTotalSet")
            for refund in order.get("refunds") or []:
                for item in (refund.get("refundLineItems") or {}).get("nodes", []):
                    product_id = str((((item.get("lineItem") or {}).get("product")) or {}).get("id") or "unknown")
                    totals[product_id]["refunded"] += int(item.get("quantity") or 0)
        ranked = sorted(totals.items(), key=lambda row: (row[1]["revenue"], row[1]["units"]), reverse=True)
        metadata = self._source(partial=order_count >= self.max_records, warnings=self._order_scope_warnings(start, end))
        return [
            {
                **metadata,
                "rank": index,
                "product_id": product_id,
                "title": item["title"],
                "units_sold": item["units"],
                "revenue": _round(item["revenue"]),
                "refund_rate_pct": round(item["refunded"] / item["units"] * 100, 2) if item["units"] else 0,
            }
            for index, (product_id, item) in enumerate(ranked[: max(1, min(top_n, 50))], 1)
        ]

    async def customer_segments(self, date_from: str, date_to: str) -> dict[str, Any]:
        demo = self._ensure_available(self._demo_customers)
        if demo is not None:
            return demo  # type: ignore[return-value]
        start, end, query = self._period(date_from, date_to)
        seen: set[str] = set()
        new = returning = guest_orders = order_count = 0
        countries: dict[str, dict[str, Any]] = defaultdict(lambda: {"orders": 0, "revenue": Decimal("0")})
        async for order in self._nodes(CUSTOMER_SEGMENTS_QUERY, "orders", variables={"query": query}):
            order_count += 1
            customer = order.get("customer") or {}
            customer_id = str(customer.get("id") or "")
            if customer_id and customer_id not in seen:
                seen.add(customer_id)
                if int(customer.get("numberOfOrders") or 0) > 1:
                    returning += 1
                else:
                    new += 1
            elif not customer_id:
                guest_orders += 1
            country = str((order.get("billingAddress") or {}).get("countryCodeV2") or "UNKNOWN")
            countries[country]["orders"] += 1
            countries[country]["revenue"] += _money_set(order, "currentTotalPriceSet")
        customer_total = new + returning
        top_countries = sorted(countries.items(), key=lambda row: row[1]["revenue"], reverse=True)[:10]
        return {
            **self._source(partial=order_count >= self.max_records, warnings=self._order_scope_warnings(start, end)),
            "new_customers": new,
            "returning_customers": returning,
            "guest_orders": guest_orders,
            "repeat_rate_pct": round(returning / customer_total * 100, 2) if customer_total else 0,
            "top_countries": [
                {"country": country, "orders": data["orders"], "revenue": _round(data["revenue"])}
                for country, data in top_countries
            ],
        }

    async def refund_stats(self, date_from: str, date_to: str) -> dict[str, Any]:
        demo = self._ensure_available(self._demo_refunds)
        if demo is not None:
            return demo  # type: ignore[return-value]
        start, end, query = self._period(date_from, date_to)
        order_count = refund_count = 0
        sales = refund_amount = Decimal("0")
        async for order in self._nodes(REFUNDS_QUERY, "orders", variables={"query": query}):
            order_count += 1
            sales += _money_set(order, "currentTotalPriceSet")
            for refund in order.get("refunds") or []:
                refund_count += 1
                refund_amount += _money_set(refund, "totalRefundedSet")
        return {
            **self._source(
                partial=order_count >= self.max_records,
                warnings=self._order_scope_warnings(start, end)
                + ["Shopify Refund 不提供统一的退款原因字段，系统不会推测原因"],
            ),
            "refund_count": refund_count,
            "refund_amount": _round(refund_amount),
            "refund_order_rate_pct": round(refund_count / order_count * 100, 2) if order_count else 0,
            "refund_value_rate_pct": round(float(refund_amount / sales * 100), 2) if sales else 0,
            "top_reasons": [],
            "reason_status": "unavailable_from_shopify_refund",
        }

    async def discount_performance(self, date_from: str, date_to: str) -> list[dict[str, Any]]:
        demo = self._ensure_available(self._demo_discounts)
        if demo is not None:
            return demo  # type: ignore[return-value]
        start, end, query = self._period(date_from, date_to)
        totals: dict[str, dict[str, Any]] = defaultdict(lambda: {"uses": 0, "sales": Decimal("0"), "discount": Decimal("0")})
        order_count = 0
        async for order in self._nodes(DISCOUNTS_QUERY, "orders", variables={"query": query}):
            order_count += 1
            codes = order.get("discountCodes") or []
            if not codes:
                continue
            sales = _money_set(order, "currentTotalPriceSet")
            discount = _money_set(order, "totalDiscountsSet")
            share_sales = sales / len(codes)
            share_discount = discount / len(codes)
            for code in codes:
                key = str(code).upper()
                totals[key]["uses"] += 1
                totals[key]["sales"] += share_sales
                totals[key]["discount"] += share_discount
        ranked = sorted(totals.items(), key=lambda row: row[1]["sales"], reverse=True)
        metadata = self._source(partial=order_count >= self.max_records, warnings=self._order_scope_warnings(start, end))
        return [
            {
                **metadata,
                "code": code,
                "usage_count": item["uses"],
                "attributed_sales": _round(item["sales"]),
                "discount_amount": _round(item["discount"]),
                "roi": _round(item["sales"] / item["discount"]) if item["discount"] else None,
                "roi_definition": "attributed_sales / discount_amount",
            }
            for code, item in ranked
        ]

    async def order_list(self, date_from: str, date_to: str, status: str = "any", limit: int = 50) -> list[dict[str, Any]]:
        demo = self._ensure_available(self._demo_order_list)
        if demo is not None:
            return demo[: max(1, min(limit, 250))]  # type: ignore[index]
        start, end, query = self._period(date_from, date_to)
        if status != "any":
            allowed = {"open", "closed", "cancelled"}
            if status not in allowed:
                raise ValueError(f"订单状态只支持: any, {', '.join(sorted(allowed))}")
            query += f" status:{status}"
        result = []
        async for order in self._nodes(
            ORDER_LIST_QUERY,
            "orders",
            variables={"query": query},
            limit=max(1, min(limit, 250)),
        ):
            money = (order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
            result.append({
                "source": "shopify_graphql",
                "order_id": order.get("id"),
                "name": order.get("name"),
                "created_at": order.get("createdAt"),
                "amount": _round(Decimal(str(money.get("amount", "0")))),
                "currency": money.get("currencyCode"),
                "financial_status": order.get("displayFinancialStatus"),
                "fulfillment_status": order.get("displayFulfillmentStatus"),
                "cancelled": bool(order.get("cancelledAt")),
                "country": (order.get("billingAddress") or {}).get("countryCodeV2"),
            })
        metadata = self._source(partial=len(result) >= max(1, min(limit, 250)), warnings=self._order_scope_warnings(start, end))
        for item in result:
            item.update(metadata)
        return result

    @staticmethod
    def _demo_base() -> dict[str, Any]:
        return {"source": "demo", "api_version": config.shopify_api_version, "is_partial": False, "warnings": ["演示数据，不代表真实店铺"]}

    def _demo_orders(self, date_from: str, date_to: str) -> dict[str, Any]:
        return {**self._demo_base(), "period": {"from": date_from, "to": date_to}, "currency": "USD", "total_orders": 342, "gmv": 18650.4, "aov": 54.53, "cancelled_orders": 12, "cancel_rate_pct": 3.5, "refund_amount": 890.2, "refund_rate_pct": 4.77}

    def _demo_abandoned(self, date_from: str, date_to: str) -> dict[str, Any]:
        return {**self._demo_base(), "period": {"from": date_from, "to": date_to}, "total_abandoned": 89, "abandoned_value": 4230.6, "recovered_count": 14, "recovery_rate_pct": 15.7, "avg_abandoned_value": 47.54, "top_abandoned_products": [{"title": "Premium Wireless Earbuds", "count": 23}]}

    def _demo_inventory(self) -> list[dict[str, Any]]:
        return [{"source": "demo", "product_id": "demo-1001", "variant_id": "demo-v1", "title": "Wireless Earbuds · Black", "sku": "WE-BLK", "inventory_quantity": 5, "low_stock": True, "safety_stock": config.shopify_low_stock_threshold}]

    def _demo_products(self) -> list[dict[str, Any]]:
        return [{"source": "demo", "rank": 1, "product_id": "demo-1001", "title": "Premium Wireless Earbuds", "units_sold": 87, "revenue": 4350.0, "refund_rate_pct": 3.4}]

    def _demo_customers(self) -> dict[str, Any]:
        return {**self._demo_base(), "new_customers": 198, "returning_customers": 144, "guest_orders": 0, "repeat_rate_pct": 42.1, "top_countries": [{"country": "US", "orders": 187, "revenue": 10230.0}]}

    def _demo_refunds(self) -> dict[str, Any]:
        return {**self._demo_base(), "refund_count": 16, "refund_amount": 890.2, "refund_order_rate_pct": 4.68, "refund_value_rate_pct": 4.77, "top_reasons": [], "reason_status": "unavailable_from_shopify_refund"}

    def _demo_discounts(self) -> list[dict[str, Any]]:
        return [{"source": "demo", "code": "SAVE20", "usage_count": 47, "attributed_sales": 2820.0, "discount_amount": 564.0, "roi": 5.0, "roi_definition": "attributed_sales / discount_amount"}]

    def _demo_order_list(self) -> list[dict[str, Any]]:
        return [{"source": "demo", "order_id": "demo-1001", "name": "#1001", "amount": 59.99, "currency": "USD", "financial_status": "PAID", "fulfillment_status": "FULFILLED", "cancelled": False, "country": "US"}]


shopify_service = ShopifyService()
