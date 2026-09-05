"""运行现有 LangGraph 循环，输出可回看的计划、步骤、重规划与报告。"""

import asyncio
from typing import AsyncGenerator, Dict, Any

from langgraph.graph import StateGraph, END
from loguru import logger

from app.agent.ops.state import PlanExecuteState
from app.agent.ops.planner import planner
from app.agent.ops.executor import executor
from app.agent.ops.replanner import replanner
from app.config import config
from app.integrations.shopify.service import shopify_service
from app.models.ops import OpsRequest
from app.services.output_safety import sanitize_model_output


def _should_end(state: PlanExecuteState) -> str:
    return "respond" if state.get("response") else "execute"


def _build_ops_graph():
    graph = StateGraph(PlanExecuteState)
    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("replanner", replanner)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "replanner")
    graph.add_conditional_edges("replanner", _should_end, {"execute": "executor", "respond": END})
    return graph.compile()


ops_graph = _build_ops_graph()


class OpsAgentService:
    timeout_seconds = 300

    async def diagnose(self, request: OpsRequest, *, history=None) -> AsyncGenerator[Dict[str, Any], None]:
        model = request.model or config.rag_model
        yield {"type": "status", "stage": "starting", "message": "正在解析日期并准备深度分析…", "model": model}
        try:
            async with asyncio.timeout(self.timeout_seconds):
                period = await shopify_service.resolve_date_range(
                    request.question, date_from=request.date_from, date_to=request.date_to,
                )
                initial_state: PlanExecuteState = {
                    "input": request.question, "plan": [], "past_steps": [], "response": "",
                    "context": {
                        **(request.extra_context or {}),
                        "date_from": period.date_from, "date_to": period.date_to,
                        "timezone": period.timezone, "period_label": period.label,
                        "session_id": request.session_id, "model": model,
                        "history": history or [],
                    },
                    "replan_count": 0, "step_status": "",
                }
                yield {"type": "status", "stage": "planning", "message": "正在制定分析计划…",
                       "model": model, "period": {"from": period.date_from, "to": period.date_to},
                       "timezone": period.timezone}
                sent_steps = 0
                remaining = []
                final_response = ""
                stream = ops_graph.astream(initial_state, config={"recursion_limit": 2 * config.max_plan_steps + 6})
                try:
                    async for event in stream:
                        for node, update in event.items():
                            # LangGraph 会把“继续原计划”的空更新表示为 None。
                            update = update or {}
                            if node == "planner":
                                remaining = update.get("plan", [])
                                if not remaining:
                                    raise ValueError("empty_plan")
                                yield {"type": "plan", "stage": "plan_created", "plan": remaining,
                                       "message": f"分析计划已制定，共 {len(remaining)} 步", "model": model}
                            elif node == "executor":
                                remaining = update.get("plan", remaining)
                                for step, result in update.get("past_steps", []):
                                    sent_steps += 1
                                    yield {"type": "step_complete", "stage": "step_executed",
                                           "step": sent_steps, "current_step": step,
                                           "status": update.get("step_status", "complete"),
                                           "result_preview": sanitize_model_output(str(result))[:500],
                                           "message": f"步骤 {sent_steps} 已执行，正在检查结果"}
                                yield {"type": "status", "stage": "evaluating",
                                       "message": "正在检查已取得的信息，决定继续、重规划或生成报告…"}
                            elif node == "replanner":
                                if update.get("response"):
                                    final_response = sanitize_model_output(str(update["response"]))[:20_000]
                                    if not final_response.strip():
                                        raise ValueError("empty_report")
                                    yield {"type": "report", "stage": "final_report", "report": final_response,
                                           "message": "运营分析报告已生成", "model": model}
                                elif "plan" in update:
                                    remaining = update["plan"]
                                    yield {"type": "replan", "stage": "plan_revised", "plan": remaining,
                                           "revision": update.get("replan_count", 0),
                                           "message": "根据执行结果调整剩余计划"}
                            if node in {"planner", "replanner"} and not final_response and remaining:
                                yield {"type": "step_start", "stage": "executing", "step": sent_steps + 1,
                                       "current_step": remaining[0], "message": f"正在执行第 {sent_steps + 1} 步"}
                finally:
                    await stream.aclose()
                if not final_response:
                    raise ValueError("missing_report")
                yield {"type": "complete", "stage": "analysis_complete", "response": final_response,
                       "message": "深度分析完成", "model": model, "source": "ops",
                       "session_id": request.session_id}
        except TimeoutError:
            yield {"type": "error", "code": "ops_timeout", "message": "分析超过时间上限，已停止；可查看已有步骤后缩小问题范围重试"}
        except Exception as exc:
            logger.warning("运营分析失败: {}", type(exc).__name__)
            yield {"type": "error", "code": "ops_failed", "message": "深度分析暂时失败，已保留执行过程，请稍后重试"}


ops_agent_service = OpsAgentService()
