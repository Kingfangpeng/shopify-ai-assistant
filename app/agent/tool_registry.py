"""17 个 Shopify 只读工具的统一候选参数 Schema 与版本注册表。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.tools.shopify_tool import (
    compare_order_periods,
    get_abandoned_checkouts,
    get_customer_segments,
    get_device_traffic,
    get_discount_performance,
    get_inventory_levels,
    get_landing_page_performance,
    get_order_list,
    get_orders_summary,
    get_product_performance,
    get_refund_stats,
    get_search_performance,
    get_traffic_geography,
    get_traffic_overview,
    get_traffic_sources,
    get_traffic_timeseries,
    get_web_performance,
)


class NoCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ComparisonCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    comparison: Literal["previous_period", "previous_year"] = "previous_period"


class LimitCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    limit: int = Field(default=20, ge=1, le=100)


class TopNCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    top_n: int = Field(default=10, ge=1, le=50)


class OrderListCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["any", "open", "closed", "cancelled"] = "any"
    limit: int = Field(default=20, ge=1, le=100)


class InventoryCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_ids: list[str] | None = Field(default=None, max_length=50)

    @field_validator("product_ids")
    @classmethod
    def valid_product_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        pattern = re.compile(r"^(?:gid://shopify/Product/)?\d{1,20}$")
        if any(not pattern.fullmatch(item) for item in value):
            raise ValueError("商品 ID 格式无效")
        return list(dict.fromkeys(value))


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    implementation: BaseTool
    candidate_schema: type[BaseModel]

    def validate_candidates(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        value = self.candidate_schema.model_validate(arguments or {})
        return value.model_dump(exclude_none=True, exclude_unset=True)

    @property
    def schema(self) -> dict[str, Any]:
        return self.candidate_schema.model_json_schema()

    @property
    def schema_hash(self) -> str:
        payload = json.dumps(self.schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def validate_execution(self, arguments: dict[str, Any]) -> dict[str, Any]:
        execution_schema = self.implementation.args_schema.model_json_schema() if self.implementation.args_schema else {}
        allowed_keys = set(execution_schema.get("properties") or {})
        unexpected = set(arguments) - allowed_keys
        if unexpected:
            raise ValueError(f"工具执行参数不允许字段: {', '.join(sorted(unexpected))}")
        candidate_keys = set(self.schema.get("properties") or {})
        candidates = {key: value for key, value in arguments.items() if key in candidate_keys}
        validated = self.validate_candidates(candidates)
        output = dict(arguments)
        output.update(validated)
        for key in ("date_from", "date_to"):
            if key in output:
                try:
                    output[key] = date.fromisoformat(str(output[key])).isoformat()
                except ValueError as exc:
                    raise ValueError(f"{key} 必须为 YYYY-MM-DD") from exc
        if "date_from" in output and "date_to" in output:
            start = date.fromisoformat(output["date_from"])
            end = date.fromisoformat(output["date_to"])
            if start > end or (end - start).days > 366:
                raise ValueError("日期范围无效或超过 366 天")
        return output


_TOOLS = (
    (compare_order_periods, ComparisonCandidates),
    (get_orders_summary, NoCandidates),
    (get_abandoned_checkouts, NoCandidates),
    (get_inventory_levels, InventoryCandidates),
    (get_product_performance, TopNCandidates),
    (get_customer_segments, NoCandidates),
    (get_refund_stats, NoCandidates),
    (get_discount_performance, NoCandidates),
    (get_order_list, OrderListCandidates),
    (get_traffic_overview, NoCandidates),
    (get_traffic_timeseries, NoCandidates),
    (get_traffic_sources, LimitCandidates),
    (get_landing_page_performance, LimitCandidates),
    (get_device_traffic, LimitCandidates),
    (get_traffic_geography, LimitCandidates),
    (get_search_performance, NoCandidates),
    (get_web_performance, NoCandidates),
)

TOOL_SPEC_REGISTRY = {
    tool.name: ToolSpec(tool.name, "1.0.0", tool, schema)
    for tool, schema in _TOOLS
}


def tool_catalog_hash() -> str:
    payload = [
        {"name": spec.name, "version": spec.version, "schema": spec.schema}
        for spec in TOOL_SPEC_REGISTRY.values()
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def planner_catalog() -> str:
    return "\n".join(
        f"- {spec.name} v{spec.version}: {spec.implementation.description.strip()}；"
        f"候选参数 Schema={json.dumps(spec.schema, ensure_ascii=False, separators=(',', ':'))}"
        for spec in TOOL_SPEC_REGISTRY.values()
    )
