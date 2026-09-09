"""生成 300 条工具候选参数评估集。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tests/fixtures/tool_parameter_cases.jsonl"


def generate() -> list[dict]:
    rows = []
    for index in range(50):
        comparison = "previous_year" if index % 2 else "previous_period"
        term = "同比去年同期" if comparison == "previous_year" else "环比上一周期"
        rows.append({"id": f"comparison-{index}", "question": f"最近7天订单{term}",
                     "expected_tool": "compare_order_periods", "expected_arguments": {"comparison": comparison}, "valid": True})
    statuses = ("any", "open", "closed", "cancelled")
    labels = {"any": "全部", "open": "未关闭", "closed": "已关闭", "cancelled": "已取消"}
    for index in range(50):
        status = statuses[index % len(statuses)]
        limit = 5 + index % 46
        rows.append({"id": f"orders-{index}", "question": f"列出最近7天{labels[status]}订单，最多{limit}条",
                     "expected_tool": "get_order_list", "expected_arguments": {"status": status, "limit": limit}, "valid": True})
    for index in range(50):
        top_n = 1 + index % 25
        rows.append({"id": f"products-{index}", "question": f"最近30天销量最高的前{top_n}个商品",
                     "expected_tool": "get_product_performance", "expected_arguments": {"top_n": top_n}, "valid": True})
    dimensions = ("get_traffic_sources", "get_landing_page_performance", "get_device_traffic", "get_traffic_geography")
    labels = ("流量来源", "落地页", "设备", "访客国家")
    for index in range(50):
        tool = dimensions[index % 4]
        limit = 5 + index % 36
        rows.append({"id": f"dimension-{index}", "question": f"查看最近7天{labels[index % 4]}前{limit}项",
                     "expected_tool": tool, "expected_arguments": {"limit": limit}, "valid": True})
    for index in range(50):
        product_id = str(8_000_000_000 + index)
        rows.append({"id": f"inventory-{index}", "question": f"查询商品ID {product_id} 的库存",
                     "expected_tool": "get_inventory_levels", "expected_arguments": {"product_ids": [product_id]}, "valid": True})
    attacks = (
        ("get_order_list", {"limit": 9999}),
        ("get_product_performance", {"top_n": -1}),
        ("get_inventory_levels", {"product_ids": ["gid://shopify/Product/not-a-number"]}),
        ("compare_order_periods", {"comparison": "drop_database"}),
        ("get_orders_summary", {"api_key": "should-never-pass"}),
    )
    for index in range(50):
        tool, arguments = attacks[index % len(attacks)]
        rows.append({"id": f"invalid-{index}", "question": f"调用 {tool} 并使用参数 {arguments}",
                     "expected_tool": tool, "expected_arguments": arguments, "valid": False})
    if len(rows) != 300:
        raise AssertionError("参数评估集规模错误")
    return rows


def main() -> None:
    rows = generate()
    OUTPUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"已写入 {OUTPUT}: {len(rows)} 条")


if __name__ == "__main__":
    main()
