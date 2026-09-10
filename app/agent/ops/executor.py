"""
Executor 节点：执行单个运营分析步骤
"""

import json
import re
from time import perf_counter
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from loguru import logger

from app.config import config
from app.agent.dispatcher import DispatchPlan, read_only_tool_dispatcher
from app.agent.tool_registry import TOOL_SPEC_REGISTRY
from app.core.llm_factory import llm_factory
from app.core.agent_context import current_agent_user_id
from app.prompts import prompt_registry
from app.services.chat.events import activity_event, emit_graph_activity
from app.tools import DEFAULT_LOCAL_AGENT_TOOLS
from .state import PlanExecuteState
from .utils import create_ops_model


def _explicit_tool_plan(task: str) -> DispatchPlan | None:
    """Planner 明确写出工具名时以该结构化标记为准，避免证据描述触发额外工具。"""
    names = tuple(
        name for name in TOOL_SPEC_REGISTRY
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", task)
    )[:4]
    if not names:
        return None
    return DispatchPlan(
        names,
        len(names) > 1,
        "执行 Planner 明确指定的只读工具",
        planner="ops_explicit_tool",
        route="shopify",
    )


async def executor(state: PlanExecuteState) -> Dict[str, Any]:
    """执行节点：执行计划中的下一个步骤"""
    logger.info("=== Executor：执行步骤 ===")

    plan = state.get("plan", [])

    if not plan:
        logger.info("计划为空，跳过执行")
        return {}

    task = plan[0]
    logger.info(f"当前任务: {task}")

    try:
        context = state.get("context") or {}
        deterministic_plan = _explicit_tool_plan(task) or read_only_tool_dispatcher.plan_all(task)
        if deterministic_plan.tools:
            started = perf_counter()
            for name in deterministic_plan.tools:
                emit_graph_activity(activity_event(
                    "tool_started", f"正在执行深度分析工具 {name}",
                    status="running", operation="tool", phase=name,
                ))
            token = current_agent_user_id.set(context.get("user_id"))
            try:
                executions = await read_only_tool_dispatcher.execute(
                    deterministic_plan,
                    task,
                    date_from=str(context.get("date_from") or ""),
                    date_to=str(context.get("date_to") or ""),
                    timezone=str(context.get("timezone") or "UTC"),
                )
            finally:
                current_agent_user_id.reset(token)
            duration_ms = (perf_counter() - started) * 1000
            for item in executions:
                emit_graph_activity(activity_event(
                    "tool_completed", f"深度分析工具 {item.name} 调用完成",
                    operation="tool", phase=item.name, duration_ms=duration_ms,
                ))
            result = json.dumps(
                {item.name: item.result for item in executions},
                ensure_ascii=False,
                default=str,
            )
            return {
                "plan": plan[1:],
                "past_steps": [(task, result)],
                "step_status": "complete",
            }

        # 获取所有可用工具
        all_tools = list(DEFAULT_LOCAL_AGENT_TOOLS)
        logger.info(f"可用只读工具数量: {len(all_tools)}")

        llm = create_ops_model(state)
        llm_with_tools = llm.bind_tools(all_tools)
        tool_node = ToolNode(all_tools)
        model_name = str(context.get("model") or config.rag_model)

        messages = [
            SystemMessage(content=prompt_registry.get("ops_executor").content),
            HumanMessage(content=(
                f"请执行以下运营分析步骤: {task}\n"
                f"用户请求上下文: {state.get('context') or {}}\n"
                "必须优先使用上下文中明确给出的 date_from/date_to。"
            ))
        ]

        # 第一步：LLM 决定是否调用工具
        selection_started = perf_counter()
        emit_graph_activity(activity_event(
            "model_call_started", "正在选择当前步骤需要的只读工具",
            status="running", operation="llm", phase="deep_tool_selection", model=model_name,
        ))
        llm_response = await llm_with_tools.ainvoke(messages)
        emit_graph_activity(activity_event(
            "model_call_completed", "步骤工具选择模型调用完成",
            operation="llm", phase="deep_tool_selection", model=model_name,
            duration_ms=(perf_counter() - selection_started) * 1000,
        ))
        logger.info(f"LLM 响应类型: {type(llm_response)}")

        # 第二步：如果有工具调用，执行工具
        if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
            logger.info(f"检测到 {len(llm_response.tool_calls)} 个工具调用")
            for call in llm_response.tool_calls:
                emit_graph_activity(activity_event(
                    "tool_started", f"正在执行深度分析工具 {call.get('name', 'unknown')}",
                    status="running", operation="tool", phase=call.get("name", "unknown"),
                ))
            messages.append(llm_response)
            tool_started = perf_counter()
            token = current_agent_user_id.set(context.get("user_id"))
            try:
                tool_messages = await tool_node.ainvoke({"messages": messages})
            finally:
                current_agent_user_id.reset(token)
            for call in llm_response.tool_calls:
                emit_graph_activity(activity_event(
                    "tool_completed", f"深度分析工具 {call.get('name', 'unknown')} 调用完成",
                    operation="tool", phase=call.get("name", "unknown"),
                    duration_ms=(perf_counter() - tool_started) * 1000,
                ))
            messages.extend(tool_messages["messages"])
            summary_started = perf_counter()
            emit_graph_activity(activity_event(
                "model_call_started", "正在整理当前步骤的工具结果",
                status="running", operation="llm", phase="deep_step_summary", model=model_name,
            ))
            final_response = await llm_with_tools.ainvoke(messages)
            emit_graph_activity(activity_event(
                "model_call_completed", "步骤结果整理模型调用完成",
                operation="llm", phase="deep_step_summary", model=model_name,
                duration_ms=(perf_counter() - summary_started) * 1000,
            ))
            result = final_response.content if hasattr(final_response, 'content') else str(final_response)
            if not isinstance(result, str) or not result.strip():
                result = "工具已执行，但当前步骤未生成可用摘要。"
        else:
            logger.warning("LLM 未调用任何工具，拒绝把模型文本当成真实数据")
            result = "未执行任何只读工具，当前步骤没有可验证的数据结果。"

        logger.info(f"步骤执行完成，结果长度: {len(result)}")

        return {
            "plan": plan[1:],
            "past_steps": [(task, result)],
            "step_status": "complete" if getattr(llm_response, "tool_calls", None) else "failed",
        }

    except Exception as exc:
        logger.error("执行步骤失败: {}", type(exc).__name__, exc_info=True)
        return {
            "plan": plan[1:],
            "past_steps": [(task, "执行失败：只读数据工具暂时不可用。")],
            "step_status": "failed",
        }
