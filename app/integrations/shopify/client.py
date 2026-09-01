"""Secure asynchronous Shopify Admin GraphQL client."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from loguru import logger

from app.config import config

SHOP_DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.myshopify\.com$")


class ShopifyError(RuntimeError):
    code = "shopify_error"


class ShopifyNotConfigured(ShopifyError):
    code = "shopify_not_configured"


class ShopifyAuthError(ShopifyError):
    code = "shopify_auth_failed"


class ShopifyPermissionError(ShopifyError):
    code = "shopify_permission_denied"


class ShopifyRateLimitError(ShopifyError):
    code = "shopify_rate_limited"


class ShopifyGraphQLError(ShopifyError):
    code = "shopify_graphql_error"


class ShopifyGraphQLClient:
    """Minimal GraphQL client with domain validation, retry and cost awareness."""

    def __init__(
        self,
        domain: str | None = None,
        token: str | None = None,
        api_version: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.domain = (domain if domain is not None else config.shopify_store_domain).strip().lower()
        self.token = (token if token is not None else config.shopify_access_token).strip()
        self.api_version = api_version or config.shopify_api_version
        self._client = http_client
        self._owns_client = http_client is None

    @property
    def configured(self) -> bool:
        return bool(
            self.domain
            and self.token
            and SHOP_DOMAIN_RE.fullmatch(self.domain)
            and not self.token.startswith("shpat_your")
            and self.token not in {"your-token", "shpat_your_token_here"}
        )

    @property
    def endpoint(self) -> str:
        if not SHOP_DOMAIN_RE.fullmatch(self.domain):
            raise ShopifyNotConfigured("Shopify 店铺域名无效")
        return f"https://{self.domain}/admin/api/{self.api_version}/graphql.json"

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        if not self.configured:
            raise ShopifyNotConfigured("Shopify 尚未配置有效的只读访问令牌")

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.token,
        }
        payload = {"query": query, "variables": variables or {}}
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                response = await self._client.post(self.endpoint, headers=headers, json=payload)
                if response.status_code == 401:
                    raise ShopifyAuthError("Shopify 凭据无效")
                if response.status_code == 403:
                    raise ShopifyPermissionError("Shopify 权限不足，请检查只读 scopes")
                if response.status_code == 429:
                    if attempt + 1 >= max_retries:
                        raise ShopifyRateLimitError("Shopify 请求受到限流")
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()

                body = response.json()
                errors = body.get("errors") or []
                if errors:
                    codes = {
                        str(item.get("extensions", {}).get("code", "")).upper()
                        for item in errors
                        if isinstance(item, dict)
                    }
                    message = "; ".join(
                        str(item.get("message", "Shopify GraphQL 请求失败"))
                        for item in errors
                        if isinstance(item, dict)
                    )[:500]
                    if "THROTTLED" in codes and attempt + 1 < max_retries:
                        await asyncio.sleep(self._graphql_retry_delay(body, attempt))
                        continue
                    if "THROTTLED" in codes:
                        raise ShopifyRateLimitError("Shopify 请求受到限流")
                    if "ACCESS_DENIED" in codes:
                        raise ShopifyPermissionError(message or "Shopify 权限不足")
                    raise ShopifyGraphQLError(message or "Shopify GraphQL 请求失败")

                data = body.get("data")
                if not isinstance(data, dict):
                    raise ShopifyGraphQLError("Shopify 返回了无效响应")
                data["_extensions"] = body.get("extensions", {})
                return data
            except (ShopifyError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, ShopifyError):
                    raise
                last_error = exc
            except (httpx.TimeoutException, httpx.NetworkError, ValueError) as exc:
                last_error = exc

            if attempt + 1 < max_retries:
                await asyncio.sleep(min(2 ** attempt, 4))

        logger.warning("Shopify GraphQL 请求失败，已耗尽重试次数: {}", type(last_error).__name__)
        raise ShopifyGraphQLError("Shopify 服务暂时不可用") from last_error

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        header = response.headers.get("Retry-After")
        if not header:
            return min(2 ** attempt, 4)
        try:
            return max(0.5, min(float(header), 10.0))
        except ValueError:
            return min(2 ** attempt, 4)

    @staticmethod
    def _graphql_retry_delay(body: dict[str, Any], attempt: int) -> float:
        throttle = body.get("extensions", {}).get("cost", {}).get("throttleStatus", {})
        available = float(throttle.get("currentlyAvailable", 0) or 0)
        restore_rate = float(throttle.get("restoreRate", 50) or 50)
        requested = float(body.get("extensions", {}).get("cost", {}).get("requestedQueryCost", 50) or 50)
        return max(0.5, min((requested - available) / restore_rate, 10.0, 2 ** attempt))
