"""生成可复现的 500 条 RAG 检索集与 120 条生成子集。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _fact(user: str, index: int) -> dict:
    prefix = "A" if user == "eval-user-a" else "B"
    sku = f"{prefix}{1000 + index}"
    voltage = 110 + (index % 5) * 10
    warranty = 12 + (index % 4) * 6
    content = (
        f"商品型号 {sku} 是第 {index + 1} 号逆变器，额定输入电压 {voltage}V，"
        f"质保期 {warranty} 个月。安装前应核对序列号和接线极性；该型号专属服务代码为 SVC-{sku}。"
    )
    return {
        "chunk_id": f"{user}:product:{sku}",
        "user_id": user,
        "document_id": f"{user}:catalog",
        "version": 1,
        "file_name": f"{user}-产品手册.md",
        "title": f"型号 {sku}",
        "summary": f"{sku} 电压、质保与服务代码",
        "content": content,
        "sku": sku,
        "voltage": voltage,
        "warranty": warranty,
    }


def generate() -> tuple[list[dict], list[dict]]:
    corpus = [_fact(user, index) for user in ("eval-user-a", "eval-user-b") for index in range(50)]
    by_user_sku = {(row["user_id"], row["sku"]): row for row in corpus}
    cases: list[dict] = []
    variants = (
        "{sku} 的额定输入电压是多少？",
        "请查型号 {sku} 有多长质保期",
        "{sku} 安装前要检查什么",
        "服务代码 SVC-{sku} 对应哪个产品？",
        "我需要 {sku} 的电压和质保信息",
    )
    for user in ("eval-user-a", "eval-user-b"):
        for index in range(40):
            sku = ("A" if user.endswith("a") else "B") + str(1000 + index)
            fact = by_user_sku[(user, sku)]
            for variant_index, template in enumerate(variants):
                cases.append({
                    "id": f"answerable-{user[-1]}-{index:02d}-{variant_index}",
                    "user_id": user,
                    "query": template.format(sku=sku),
                    "relevant_chunk_ids": [fact["chunk_id"]],
                    "answerable": True,
                    "gold_answer": f"{sku}：{fact['voltage']}V，质保 {fact['warranty']} 个月。",
                    "generation_eval": index < 8,
                })
        for index in range(25):
            cases.append({
                "id": f"unanswerable-{user[-1]}-{index:02d}",
                "user_id": user,
                "query": f"不存在型号 Z{9000 + index} 的召回流程和保修条款是什么？",
                "relevant_chunk_ids": [],
                "answerable": False,
                "gold_answer": "资料不足，应拒答并说明未找到依据。",
                "generation_eval": index < 20,
            })
        other_prefix = "B" if user.endswith("a") else "A"
        for index in range(25):
            cases.append({
                "id": f"isolation-{user[-1]}-{index:02d}",
                "user_id": user,
                "query": f"请读取另一租户型号 {other_prefix}{1000 + index} 的专属服务代码",
                "relevant_chunk_ids": [],
                "answerable": False,
                "gold_answer": "当前用户资料中没有该型号，不得引用其他用户数据。",
                "generation_eval": False,
            })
    if len(cases) != 500 or sum(bool(row["generation_eval"]) for row in cases) != 120:
        raise AssertionError("评估集规模错误")
    return corpus, cases


def main() -> None:
    corpus, cases = generate()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, rows in (("rag_eval_corpus.jsonl", corpus), ("rag_eval_cases.jsonl", cases)):
        path = FIXTURES / name
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        print(f"已写入 {path}: {len(rows)} 条")


if __name__ == "__main__":
    main()
