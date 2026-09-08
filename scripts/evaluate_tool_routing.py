"""用带标准答案的问题集评估聊天 Agent 的只读工具路由准确率。"""

from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from loguru import logger


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.agent.dispatcher import LOCAL_TOOL_REGISTRY  # noqa: E402
from app.config import config  # noqa: E402
from app.services.chat.agent_service import chat_agent_service  # noqa: E402
from app.services.model_catalog_service import model_catalog_service  # noqa: E402
from app.prompts import prompt_registry  # noqa: E402


DEFAULT_CASES = ROOT / "tests" / "fixtures" / "tool_routing_cases.json"
KNOWN_ROUTES = {"shopify", "knowledge", "mixed", "chat", "clarify", "unsupported"}


@dataclass(frozen=True)
class EvaluationResult:
    case_id: str
    category: str
    question: str
    expected_tools: tuple[str, ...]
    actual_tools: tuple[str, ...]
    planner: str
    exact: bool
    missing_tools: tuple[str, ...]
    extra_tools: tuple[str, ...]
    elapsed_ms: int
    error: str | None = None
    route: str = ""
    expected_route: str | None = None


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("评估问题集必须是非空 JSON 数组")
    known_tools = set(LOCAL_TOOL_REGISTRY)
    seen_ids: set[str] = set()
    for index, case in enumerate(payload, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"第 {index} 条用例不是对象")
        case_id = str(case.get("id") or "")
        question = str(case.get("question") or "").strip()
        expected = case.get("expected_tools")
        if not case_id or case_id in seen_ids:
            raise ValueError(f"第 {index} 条用例 ID 缺失或重复: {case_id}")
        if not question or not isinstance(expected, list):
            raise ValueError(f"用例 {case_id} 缺少问题或 expected_tools")
        unknown = set(expected) - known_tools
        if unknown:
            raise ValueError(f"用例 {case_id} 使用未知工具: {sorted(unknown)}")
        seen_ids.add(case_id)
    return payload


def load_suite_manifest(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """读取套件清单，并在运行模型前验证条数、摘要和跨文件唯一性。"""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("评估套件清单必须包含 files 数组")
    cases: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or not entry.get("path"):
            raise ValueError("评估套件清单包含无效文件项")
        case_path = (path.parent / str(entry["path"])).resolve()
        if not case_path.is_file():
            raise ValueError(f"评估文件不存在: {case_path}")
        digest = hashlib.sha256(case_path.read_bytes()).hexdigest()
        if digest != entry.get("sha256"):
            raise ValueError(f"评估文件摘要不匹配: {case_path.name}")
        rows = load_cases(case_path)
        if len(rows) != entry.get("cases"):
            raise ValueError(f"评估文件条数不匹配: {case_path.name}")
        cases.extend(rows)
        source_files.append({"path": str(case_path), "cases": len(rows), "sha256": digest})

    if len(cases) != manifest.get("total_cases"):
        raise ValueError("评估套件总条数与清单不一致")
    ids = [str(case["id"]) for case in cases]
    questions = [str(case["question"]).strip() for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("评估套件包含跨文件重复 ID")
    if len(questions) != len(set(questions)):
        raise ValueError("评估套件包含跨文件重复问题")
    unknown_routes = {
        str(case.get("expected_route")) for case in cases
        if case.get("expected_route") not in KNOWN_ROUTES
    }
    if unknown_routes:
        raise ValueError(f"评估套件包含未知路由: {sorted(unknown_routes)}")
    return cases, {
        "manifest_path": str(path.resolve()),
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "suite_version": manifest.get("suite_version"),
        "seed": manifest.get("seed"),
        "files": source_files,
    }


async def evaluate_case(
    case: dict[str, Any],
    model: str,
    semaphore: asyncio.Semaphore,
) -> EvaluationResult:
    expected = tuple(dict.fromkeys(str(name) for name in case["expected_tools"]))
    started = perf_counter()
    actual: tuple[str, ...] = ()
    planner = "error"
    error: str | None = None
    route = ""
    try:
        history = list(case.get("history") or [])
        async with semaphore:
            started = perf_counter()
            plan = await chat_agent_service.resolve_plan(case["question"], history, model)
        actual = plan.tools
        planner = plan.planner
        route = plan.route
    except Exception as exc:  # 评估必须继续并把单条异常计为错误
        error = f"{type(exc).__name__}: {getattr(exc, 'code', 'evaluation_failed')}"

    expected_set = set(expected)
    actual_set = set(actual)
    return EvaluationResult(
        case_id=case["id"],
        category=str(case.get("category") or "未分类"),
        question=case["question"],
        expected_tools=expected,
        actual_tools=actual,
        planner=planner,
        exact=(expected_set == actual_set and error is None
               and (not case.get("expected_route") or route == case["expected_route"])),
        missing_tools=tuple(sorted(expected_set - actual_set)),
        extra_tools=tuple(sorted(actual_set - expected_set)),
        elapsed_ms=round((perf_counter() - started) * 1000),
        error=error,
        route=route,
        expected_route=case.get("expected_route"),
    )


def calculate_metrics(results: list[EvaluationResult]) -> dict[str, Any]:
    total = len(results)
    exact_count = sum(result.exact for result in results)
    true_positive = sum(len(set(result.expected_tools) & set(result.actual_tools)) for result in results)
    false_positive = sum(len(result.extra_tools) for result in results)
    false_negative = sum(len(result.missing_tools) for result in results)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negative_results = [result for result in results if not result.expected_tools]
    negative_correct = sum(result.exact for result in negative_results)
    category_rows: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in results:
        grouped[result.category].append(result)
    for category, rows in grouped.items():
        correct = sum(row.exact for row in rows)
        category_rows[category] = {
            "correct": correct,
            "total": len(rows),
            "accuracy": correct / len(rows),
        }
    route_confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for result in results:
        expected_route = result.expected_route or "未标注"
        actual_route = result.route or ("异常" if result.error else "空路由")
        route_confusion[expected_route][actual_route] += 1
    route_total = sum(result.expected_route is not None for result in results)
    route_correct = sum(
        result.expected_route is not None and result.expected_route == result.route and result.error is None
        for result in results
    )
    latencies = sorted(result.elapsed_ms for result in results)

    def percentile(percent: float) -> int:
        if not latencies:
            return 0
        index = max(0, min(len(latencies) - 1, int((len(latencies) - 1) * percent + 0.5)))
        return latencies[index]

    repetitions: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in results:
        repetitions[result.case_id].append(result)
    repeated_cases = {case_id: rows for case_id, rows in repetitions.items() if len(rows) > 1}
    stable_cases = sum(
        len({(row.route, row.actual_tools, row.error) for row in rows}) == 1
        for rows in repeated_cases.values()
    )
    return {
        "total": total,
        "unique_cases": len(repetitions),
        "exact_count": exact_count,
        "exact_accuracy": exact_count / total if total else 0.0,
        "tool_precision": precision,
        "tool_recall": recall,
        "tool_f1": f1,
        "negative_correct": negative_correct,
        "negative_total": len(negative_results),
        "negative_accuracy": negative_correct / len(negative_results) if negative_results else 1.0,
        "categories": category_rows,
        "route_correct": route_correct,
        "route_total": route_total,
        "route_accuracy": route_correct / route_total if route_total else 1.0,
        "route_confusion_matrix": {
            expected: dict(sorted(actual.items()))
            for expected, actual in sorted(route_confusion.items())
        },
        "planners": dict(Counter(result.planner for result in results)),
        "mean_latency_ms": round(sum(result.elapsed_ms for result in results) / total) if total else 0,
        "p50_latency_ms": percentile(0.50),
        "p95_latency_ms": percentile(0.95),
        "p99_latency_ms": percentile(0.99),
        "stable_cases": stable_cases,
        "repeated_cases": len(repeated_cases),
        "repeat_stability": stable_cases / len(repeated_cases) if repeated_cases else None,
        "errors": sum(result.error is not None for result in results),
    }


def print_report(model: str, metrics: dict[str, Any], results: list[EvaluationResult]) -> None:
    print(f"\n工具路由评估模型: {model}")
    print(f"用例数: {metrics['total']}")
    print(f"严格准确率: {metrics['exact_count']}/{metrics['total']} = {metrics['exact_accuracy']:.2%}")
    print(
        "工具级指标: "
        f"Precision {metrics['tool_precision']:.2%} / "
        f"Recall {metrics['tool_recall']:.2%} / F1 {metrics['tool_f1']:.2%}"
    )
    print(
        "无业务查询题准确率: "
        f"{metrics['negative_correct']}/{metrics['negative_total']} = {metrics['negative_accuracy']:.2%}"
    )
    print(
        "路由准确率: "
        f"{metrics['route_correct']}/{metrics['route_total']} = {metrics['route_accuracy']:.2%}"
    )
    print("\n分类准确率:")
    for category, row in metrics["categories"].items():
        print(f"  {category:<10} {row['correct']:>2}/{row['total']:<2} {row['accuracy']:>7.2%}")
    print(f"\n路由混淆矩阵: {metrics['route_confusion_matrix']}")
    print(f"规划来源: {metrics['planners']}")
    stability = (
        f"{metrics['repeat_stability']:.2%}"
        if metrics["repeat_stability"] is not None else "未测（需 --repeat 至少为 2）"
    )
    print(
        "规划耗时（不含排队）: "
        f"平均 {metrics['mean_latency_ms']} ms / P50 {metrics['p50_latency_ms']} ms / "
        f"P95 {metrics['p95_latency_ms']} ms / P99 {metrics['p99_latency_ms']} ms；"
        f"重复稳定率: {stability}；失败请求: {metrics['errors']}"
    )

    failures = [result for result in results if not result.exact]
    if not failures:
        print("\n全部用例通过。")
        return
    detail_limit = 100
    print(f"\n错题明细 ({len(failures)}，最多显示 {detail_limit} 条):")
    for result in failures[:detail_limit]:
        expected = ", ".join(result.expected_tools) or "不调用 Shopify 工具"
        actual = ", ".join(result.actual_tools) or "未调用"
        print(f"  [{result.case_id}] {result.question}")
        print(f"    期望: {expected}")
        print(f"    实际: {actual} ({result.planner}, {result.elapsed_ms}ms)")
        if result.expected_route:
            print(f"    路由: 期望 {result.expected_route} / 实际 {result.route}")
        if result.error:
            print(f"    异常: {result.error}")
    if len(failures) > detail_limit:
        print(f"  其余 {len(failures) - detail_limit} 条请查看 JSON 报告。")


async def run(args: argparse.Namespace) -> int:
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    source: dict[str, Any]
    if args.suite:
        cases, source = load_suite_manifest(args.suite)
    else:
        case_path = args.cases or DEFAULT_CASES
        cases = load_cases(case_path)
        source = {
            "cases_path": str(case_path.resolve()),
            "cases_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(),
        }
    if args.category:
        cases = [case for case in cases if case.get("category") == args.category]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise ValueError("筛选后没有可执行的评估用例")

    model = await model_catalog_service.resolve_model(args.model or config.rag_model)
    semaphore = asyncio.Semaphore(args.concurrency)
    results = []
    for repetition in range(args.repeat):
        for start in range(0, len(cases), args.batch_size):
            batch = cases[start:start + args.batch_size]
            rows = await asyncio.gather(*(evaluate_case(case, model, semaphore) for case in batch))
            results.extend(rows)
            completed = start + len(batch)
            print(
                f"进度: 第 {repetition + 1}/{args.repeat} 轮，"
                f"{completed}/{len(cases)} 条",
                flush=True,
            )
    metrics = calculate_metrics(results)
    print_report(model, metrics, results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {"model": model, "repeat": args.repeat,
                 "evaluator": {
                     "provider": "local_ollama" if config.local_llm_only else "openai_compatible",
                     "model": model,
                 },
                 "prompt_bundle": prompt_registry.bundle("routing"),
                 "note": (
                     "本报告为本地 Qwen 评估；历史 DeepSeek 报告仅作为旧基线。"
                     if config.local_llm_only else "本报告使用当前 OpenAI 兼容服务。"
                 ),
                 "timestamp": datetime.now(timezone.utc).isoformat(),
                 "source": source,
                 "planner_sha256": hashlib.sha256((ROOT / "app/agent/semantic_planner.py").read_bytes()).hexdigest(),
                 "metrics": metrics, "results": [asdict(result) for result in results]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON 报告: {args.output.resolve()}")
    return 0 if metrics["exact_accuracy"] >= args.minimum_accuracy else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估聊天 Agent 是否为问题选择了正确的只读工具")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--cases", type=Path, help="单个 JSON 问题集路径；默认使用旧回归集")
    source.add_argument("--suite", type=Path, help="评估套件 manifest.json 路径")
    parser.add_argument("--model", help="评估模型；默认使用 RAG_MODEL")
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 6), help="重复次数，分别运行相同用例")
    parser.add_argument("--category", help="只执行一个分类")
    parser.add_argument("--limit", type=int, default=0, help="只运行前 N 条用例")
    parser.add_argument("--concurrency", type=int, default=3, choices=range(1, 9), help="模型规划并发数")
    parser.add_argument("--batch-size", type=int, default=100, choices=range(1, 501), help="每批提交的用例数")
    parser.add_argument("--minimum-accuracy", type=float, default=0.0, help="低于阈值时返回退出码 1")
    parser.add_argument("--output", type=Path, help="可选 JSON 报告路径")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
