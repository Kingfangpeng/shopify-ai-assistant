"""运营 Agent 服务 - 接通 LangGraph Plan-Execute-Replan 图"""

import json
from typing import AsyncGenerator, Dict, Any

from langgraph.graph import StateGraph, END
from loguru import logger

from app.agent.ops.state import PlanExecuteState
from app.agent.ops.planner import planner
from app.agent.ops.executor import executor
from app.agent.ops.replanner import replanner
from app.config import config
from app.models.ops import OpsRequest


def _should_end(state: PlanExecuteState) -> str:
    """路由函数：决定下一步去 executor 还是结束"""
    if state.get("response"):
        return "respond"
    replan_count = state.get("replan_count", 0)
    if replan_count >= config.max_replan_count:
        return "respond"
    return "execute"


def _build_ops_graph():
    """构建并编译 Plan-Execute-Replan 图"""
    graph = StateGraph(PlanExecuteState)

    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("replanner", replanner)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "replanner")
    graph.add_conditional_edges(
        "replanner",
        _should_end,
        {
            "execute": "executor",
            "respond": END,
        }
    )

    return graph.compile()


# 全局编译好的图（启动时初始化一次）
ops_graph = _build_ops_graph()


class OpsAgentService:
    """运营 Agent 服务"""

    async def diagnose(
        self,
        request: OpsRequest,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行 Plan-Execute-Replan Agent，流式输出分析过程和结果。

        SSE 事件类型：
        - status: 状态更新
        - plan: 计划制定完成
        - step_complete: 单步执行完成
        - report: 最终报告
        - complete: 分析完成
        - error: 错误
        """
        logger.info(f"[{request.session_id}] 开始运营分析: {request.question}")

        try:
            yield {
                "type": "status",
                "stage": "starting",
                "message": "正在启动运营分析 Agent...",
            }

            initial_state: PlanExecuteState = {
                "input": request.question,
                "plan": [],
                "past_steps": [],
                "response": "",
                "context": {
                    "date_from": request.date_from,
                    "date_to": request.date_to,
                    "session_id": request.session_id,
                    **(request.extra_context or {}),
                },
                "replan_count": 0,
            }

            # 追踪已发送的步骤数，避免重复发送
            sent_steps = 0
            final_response = ""

            async for event in ops_graph.astream(initial_state):
                # event 是 {node_name: state_update} 格式
                for node_name, state_update in event.items():

                    if node_name == "planner":
                        plan = state_update.get("plan", [])
                        if plan:
                            logger.info(f"计划制定完成，共 {len(plan)} 步")
                            yield {
                                "type": "plan",
                                "stage": "plan_created",
                                "message": f"分析计划已制定，共 {len(plan)} 个步骤",
                                "plan": plan,
                            }

                    elif node_name == "executor":
                        past_steps = state_update.get("past_steps", [])
                        new_steps = past_steps[sent_steps:]
                        for step, result in new_steps:
                            sent_steps += 1
                            yield {
                                "type": "step_complete",
                                "stage": "step_executed",
                                "message": f"步骤执行完成 ({sent_steps})",
                                "current_step": step,
                                "result_preview": result[:200] + "..." if len(result) > 200 else result,
                            }

                    elif node_name == "replanner":
                        response = state_update.get("response", "")
                        if response and response != final_response:
                            final_response = response
                            yield {
                                "type": "report",
                                "stage": "final_report",
                                "message": "运营分析报告已生成",
                                "report": response,
                            }

            yield {
                "type": "complete",
                "stage": "analysis_complete",
                "message": "运营分析完成",
                "response": final_response,
            }
            logger.info(f"[{request.session_id}] 运营分析完成")

        except Exception as e:
            logger.error(f"[{request.session_id}] 运营分析失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "stage": "error",
                "message": f"运营分析失败: {str(e)}",
            }


ops_agent_service = OpsAgentService()
