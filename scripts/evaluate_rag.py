"""在独立 Milvus 集合上评估 dense、BM25、RRF 与 FlashRank，不调用外部 LLM。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from statistics import mean

from langchain_core.documents import Document
from loguru import logger

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
        "【{} v{} {}】 {}".format(
            doc.metadata.get("file_name", "未知来源"),
            doc.metadata.get("version", "?"),
            citation_id(doc),
            doc.page_content,
        )
        for doc in documents
    ) or "无可用资料"
    # 生成子集只验证受证据约束的短回答和引用，不需要长思考链。
    # Ollama 的 OpenAI 兼容端点使用 reasoning_effort=none 关闭思考；
    # `think=false` 属于原生 /api/chat 参数，在兼容端点会被忽略。
    model = llm_factory.create_chat_model(
        model=config.rag_model,
        temperature=0,
        streaming=False,
        extra_body={"reasoning_effort": "none"},
    ).bind(max_tokens=128)
    response = await model.ainvoke([
        ("system", prompt_registry.get("rag_answer").content),
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
        # 门槛针对预热后的在线延迟，先加载索引、Embedding 连接和 ONNX 会话。
        for _ in range(3):
            manager.evaluate_search(cases[0]["query"], mode, 10, cases[0]["user_id"])
        results = []
        for index, case in enumerate(cases, 1):
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
            if index % 100 == 0:
                print(f"检索评估进度: {mode} {index}/{len(cases)}", flush=True)
        report["strategies"][mode] = summarize(results)

    if args.include_generation:
        generation_cases = [row for row in cases if row["generation_eval"]]
        semaphore = asyncio.Semaphore(max(1, min(args.generation_concurrency, 8)))

        async def evaluate_generation(case: dict) -> dict:
            async with semaphore:
                answer = await generate_answer(case["query"], cached[case["id"]])
            cited = {
                chunk_id for chunk_id in (citation_id(doc) for doc in cached[case["id"]])
                if chunk_id and chunk_id in answer
            }
            relevant = set(case["relevant_chunk_ids"])
            refusal = "资料不足" in answer or "无法回答" in answer
            return {
                "id": case["id"],
                "citation_accurate": bool(relevant and relevant.intersection(cited)) if case["answerable"] else not cited,
                "correct_refusal": refusal if not case["answerable"] else not refusal,
            }

        generation = []
        for start in range(0, len(generation_cases), 12):
            generation.extend(await asyncio.gather(*(
                evaluate_generation(case) for case in generation_cases[start:start + 12]
            )))
            print(f"生成评估进度: {min(start + 12, len(generation_cases))}/{len(generation_cases)}", flush=True)
        no_answer = [
            row for row, case in zip(generation, generation_cases)
            if not case["answerable"]
        ]
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
    if "generation" in report:
        report["thresholds"].update({
            "citation_accuracy": {
                "target": 0.95,
                "passed": report["generation"]["citation_accuracy"] >= 0.95,
            },
            "no_answer_refusal_rate": {
                "target": 0.95,
                "passed": report["generation"]["no_answer_refusal_rate"] >= 0.95,
            },
        })
    report["passed"] = all(item["passed"] for item in report["thresholds"].values())
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--corpus", type=Path, default=ROOT / "tests/fixtures/rag_eval_corpus.jsonl")
    value.add_argument("--cases", type=Path, default=ROOT / "tests/fixtures/rag_eval_cases.jsonl")
    value.add_argument("--output", type=Path, default=ROOT / "output/rag-evaluation-local-qwen.json")
    value.add_argument("--collection", default="shopify_rag_eval_v1")
    value.add_argument("--include-generation", action="store_true")
    value.add_argument("--generation-concurrency", type=int, default=3)
    return value


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    args = parser().parse_args()
    report = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
