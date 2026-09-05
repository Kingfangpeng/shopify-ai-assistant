"""显式付费用量测试：真实模型 + 合成只读数据，验证完整循环，不访问真实店铺。"""

import argparse
import asyncio
import importlib
import json
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from langchain_core.tools import tool
from loguru import logger
from app.agent.dispatcher import read_only_tool_dispatcher, ToolExecution
from app.core.llm_factory import llm_factory
from app.integrations.shopify.dates import StoreDateRange
from app.models.ops import OpsRequest

SAMPLE = {"source": "test_fixture", "total_orders": 6, "gmv": 600, "refund_amount": 20, "currency": "EUR"}


@tool
def get_orders_summary(date_from: str = "", date_to: str = "") -> dict:
    """读取合成订单数据，仅限测试，不访问真实店铺。"""
    return SAMPLE


async def execute(plan, *_args, **_kwargs):
    return [ToolExecution(name, SAMPLE) for name in plan.tools]


async def run(model):
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    planner = importlib.import_module("app.agent.ops.planner")
    executor = importlib.import_module("app.agent.ops.executor")
    replanner = importlib.import_module("app.agent.ops.replanner")
    service = importlib.import_module("app.services.ops_agent_service")
    started = perf_counter()
    used = []
    original = llm_factory.create_chat_model

    def create(**kwargs):
        used.append(kwargs.get("model"))
        return original(**kwargs)

    with (
        patch.object(planner, "retrieve_knowledge", SimpleNamespace(ainvoke=AsyncMock(return_value="没有相关资料"))),
        patch.object(planner, "DEFAULT_LOCAL_AGENT_TOOLS", (get_orders_summary,)),
        patch.object(executor, "DEFAULT_LOCAL_AGENT_TOOLS", (get_orders_summary,)),
        patch.object(replanner, "DEFAULT_LOCAL_AGENT_TOOLS", (get_orders_summary,)),
        patch.object(read_only_tool_dispatcher, "execute", execute),
        patch.object(service.shopify_service, "resolve_date_range", AsyncMock(return_value=StoreDateRange(
            "2026-09-01", "2026-09-03", "Asia/Shanghai", "合成测试周期", "2026-09-04",
        ))),
        patch.object(llm_factory, "create_chat_model", create),
    ):
        events = []
        question = "这是合成数据兼容性测试，不是真实店铺。读取样例订单，核对金额和币种，然后生成简短中文报告，明确数据局限，不得虚构业绩提升比例。计划保持简短。"
        async for event in service.ops_agent_service.diagnose(OpsRequest(question=question, model=model)):
            events.append(event)
            print(json.dumps(event, ensure_ascii=False), flush=True)
    result = {"model": model, "elapsed_seconds": round(perf_counter() - started, 2),
              "model_instances": len(used), "all_nodes_used_selected_model": bool(used) and set(used) == {model},
              "event_types": [event["type"] for event in events], "completed": events[-1]["type"] == "complete"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["completed"] and result["all_nodes_used_selected_model"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="将调用已配置的模型服务并产生用量")
    raise SystemExit(asyncio.run(run(parser.parse_args().model)))
