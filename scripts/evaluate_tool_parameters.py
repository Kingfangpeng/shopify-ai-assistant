"""使用当前本地规划模型运行 300 条候选参数回归。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.agent.semantic_planner import semantic_tool_planner
from app.agent.tool_registry import TOOL_SPEC_REGISTRY
from app.config import config
from app.prompts import prompt_registry


ROOT = Path(__file__).resolve().parents[1]


async def run(cases: list[dict], model: str, concurrency: int = 3) -> dict:
    tools = tuple(spec.implementation for spec in TOOL_SPEC_REGISTRY.values())
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 8)))

    async def evaluate(case: dict) -> dict:
        async with semaphore:
            started = time.perf_counter()
            plan = await semantic_tool_planner.plan(case["question"], model, tools, [])
            latency = (time.perf_counter() - started) * 1000
        correct = 0
        total_fields = 0
        illegal_executions = 0
        failures = []
        if case["valid"]:
            expected = case["expected_arguments"]
            total_fields += len(expected) + 1
            if plan and case["expected_tool"] in plan.tools:
                correct += 1
                actual = dict(plan.candidate_arguments.get(case["expected_tool"]) or {})
                for key, value in expected.items():
                    if actual.get(key) == value:
                        correct += 1
                    else:
                        failures.append({"id": case["id"], "field": key, "expected": value, "actual": actual.get(key)})
            else:
                failures.append({"id": case["id"], "field": "tool", "expected": case["expected_tool"],
                                 "actual": list(plan.tools) if plan else None})
        elif plan:
            try:
                for name, arguments in plan.candidate_arguments.items():
                    TOOL_SPEC_REGISTRY[name].validate_candidates(arguments)
            except Exception:
                illegal_executions += 1
        return {
            "correct": correct,
            "total_fields": total_fields,
            "illegal_executions": illegal_executions,
            "failures": failures,
            "latency": latency,
        }

    rows = []
    for start in range(0, len(cases), 25):
        rows.extend(await asyncio.gather(*(evaluate(case) for case in cases[start:start + 25])))
        print(f"参数评估进度: {min(start + 25, len(cases))}/{len(cases)}", flush=True)
    correct = sum(row["correct"] for row in rows)
    total_fields = sum(row["total_fields"] for row in rows)
    illegal_executions = sum(row["illegal_executions"] for row in rows)
    failures = [failure for row in rows for failure in row["failures"]]
    latencies = [row["latency"] for row in rows]
    return {
        "dataset_cases": len(cases),
        "evaluator": {"provider": "local_ollama", "model": model},
        "prompt_bundle": prompt_registry.bundle("routing"),
        "field_accuracy": correct / total_fields if total_fields else 0,
        "illegal_parameter_execution_count": illegal_executions,
        "target": {"field_accuracy": 0.98, "illegal_parameter_execution_count": 0},
        "passed": correct / total_fields >= 0.98 and illegal_executions == 0,
        "latency_ms": {"average": sum(latencies) / len(latencies), "max": max(latencies)},
        "failures": failures[:100],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=ROOT / "tests/fixtures/tool_parameter_cases.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "output/tool-parameter-evaluation-local-qwen.json")
    parser.add_argument("--model", default=config.llm_model)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        cases = cases[:args.limit]
    report = asyncio.run(run(cases, args.model, args.concurrency))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
