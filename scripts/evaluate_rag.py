"""在独立 Milvus 集合上评估 dense、BM25、RRF 与 FlashRank，不调用外部 LLM。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path
from statistics import mean

from langchain_core.documents import Document

from app.config import config
from app.core.llm_factory import llm_factory
from app.services.vector_store_manager import VectorStoreManager
from app.prompts import prompt_registry


ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    return next((1 / index for index, value in enumerate(retrieved, 1) if value in relevant), 0.0)


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int = 10) -> float:
    if not relevant:
        return 1.0
    dcg = sum(1 / math.log2(index + 1) for index, value in enumerate(retrieved[:k], 1) if value in relevant)
    ideal = sum(1 / math.log2(index + 1) for index in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)] if ordered else 0.0


def summarize(rows: list[dict]) -> dict:
    answerable = [row for row in rows if row["answerable"]]
    return {
        "cases": len(rows),
        "recall_at_5": mean(row["recall_at_5"] for row in answerable) if answerable else 0,
        "mrr_at_10": mean(row["reciprocal_rank"] for row in answerable) if answerable else 0,
        "ndcg_at_10": mean(row["ndcg_at_10"] for row in answerable) if answerable else 0,
        "permission_leakage_rate": mean(row["permission_leakage"] for row in rows),
        "latency_p95_ms": p95([row["latency_ms"] for row in rows]),
    }


def citation_id(document: Document) -> str:
    return str(document.metadata.get("chunk_id") or "")


async def generate_answer(query: str, documents: list[Document]) -> str:
    evidence = "\n".join(
        f"[{citation_id(doc)}] {doc.page_content}" for doc in documents
    ) or "无可用资料"
    model = llm_factory.create_chat_model(model=config.rag_model, temperature=0, streaming=False)
    response = await model.ainvoke([
        ("system", "只能依据资料回答。资料无答案时明确回复“资料不足，无法回答”。每个事实必须引用方括号中的 chunk_id。"),
        ("user", f"资料：\n{evidence}\n\n问题：{query}"),
    ])
    return str(getattr(response, "content", response))


async def run(args: argparse.Namespace) -> dict:
    corpus = load_jsonl(args.corpus)
    cases = load_jsonl(args.cases)
    manager = VectorStoreManager(collection_name=args.collection, alias_name=None)
    manager.vector_store = manager._make_store(args.collection, drop_old=True)
    documents = [Document(
        page_content=row["content"],
        metadata={key: row[key] for key in (
            "chunk_id", "user_id", "document_id", "version", "file_name", "title", "summary"
        )},
    ) for row in corpus]
    manager.add_documents(documents, ids=[row["chunk_id"] for row in corpus])

    report = {
        "dataset": {"retrieval_cases": len(cases), "generation_cases": sum(row["generation_eval"] for row in cases)},
        "evaluator": {"provider": "local_ollama", "model": config.rag_model},
        "prompt_bundle": prompt_registry.bundle("rag_answer"),
        "note": "本报告为本地 Qwen/确定性指标评估；历史 DeepSeek 报告不作为改造后结果。",
        "strategies": {},
    }
    cached: dict[str, list[Document]] = {}
    for mode in ("dense", "bm25", "rrf", "rrf+flashrank"):
        results = []
        for case in cases:
            started = time.perf_counter()
            docs = manager.evaluate_search(case["query"], mode, 10, case["user_id"])
            elapsed = (time.perf_counter() - started) * 1000
            retrieved = [citation_id(doc) for doc in docs]
            relevant = set(case["relevant_chunk_ids"])
            results.append({
                "id": case["id"],
                "answerable": case["answerable"],
                "recall_at_5": float(bool(relevant.intersection(retrieved[:5]))),
                "reciprocal_rank": reciprocal_rank(retrieved[:10], relevant),
                "ndcg_at_10": ndcg_at_k(retrieved, relevant),
                "permission_leakage": float(any(doc.metadata.get("user_id") != case["user_id"] for doc in docs)),
                "latency_ms": elapsed,
            })
            if mode == "rrf+flashrank" and case["generation_eval"]:
                cached[case["id"]] = docs
        report["strategies"][mode] = summarize(results)

    if args.include_generation:
        generation = []
        for case in (row for row in cases if row["generation_eval"]):
            answer = await generate_answer(case["query"], cached[case["id"]])
            cited = {chunk_id for chunk_id in (citation_id(doc) for doc in cached[case["id"]]) if f"[{chunk_id}]" in answer}
            relevant = set(case["relevant_chunk_ids"])
            refusal = "资料不足" in answer or "无法回答" in answer
            generation.append({
                "id": case["id"],
                "citation_accurate": bool(relevant and relevant.intersection(cited)) if case["answerable"] else not cited,
                "correct_refusal": refusal if not case["answerable"] else not refusal,
            })
        no_answer = [row for row, case in zip(generation, (row for row in cases if row["generation_eval"])) if not case["answerable"]]
        report["generation"] = {
            "citation_accuracy": mean(row["citation_accurate"] for row in generation),
            "no_answer_refusal_rate": mean(row["correct_refusal"] for row in no_answer),
            "cases": len(generation),
        }

    final = report["strategies"]["rrf+flashrank"]
    report["thresholds"] = {
        "recall_at_5": {"target": 0.95, "passed": final["recall_at_5"] >= 0.95},
        "mrr_at_10": {"target": 0.90, "passed": final["mrr_at_10"] >= 0.90},
        "ndcg_at_10": {"target": 0.90, "passed": final["ndcg_at_10"] >= 0.90},
        "permission_leakage_rate": {"target": 0, "passed": final["permission_leakage_rate"] == 0},
        "latency_p95_ms": {"target": 1500, "passed": final["latency_p95_ms"] <= 1500},
    }
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--corpus", type=Path, default=ROOT / "tests/fixtures/rag_eval_corpus.jsonl")
    value.add_argument("--cases", type=Path, default=ROOT / "tests/fixtures/rag_eval_cases.jsonl")
    value.add_argument("--output", type=Path, default=ROOT / "output/rag-evaluation-local-qwen.json")
    value.add_argument("--collection", default="shopify_rag_eval_v1")
    value.add_argument("--include-generation", action="store_true")
    return value


def main() -> None:
    args = parser().parse_args()
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
