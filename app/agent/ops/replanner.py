"""
Replanner 节点：重新规划或生成最终运营报告
"""

from textwrap import dedent
from typing import Dict, Any, List, Literal
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from loguru import logger

from app.config import config
from app.core.llm_factory import llm_factory
from app.tools import DEFAULT_LOCAL_AGENT_TOOLS
from .state import PlanExecuteState
from .utils import format_tools_description, create_ops_model
from app.services.output_safety import sanitize_model_output
from app.prompts import prompt_registry
from app.agent.tool_registry import TOOL_SPEC_REGISTRY


def _has_explicit_data_step(steps: list[str]) -> bool:
    """仍有 Planner 明确点名的数据工具时，不允许提前结束。"""
    return any(name in step for step in steps for name in TOOL_SPEC_REGISTRY)


class Response(BaseModel):
    """最终响应格式"""
    response: str = Field(description="对用户的最终运营分析报告（Markdown 格式）")


class Act(BaseModel):
    """重新规划的输出格式"""
    action: Literal["continue", "replan", "respond"] = Field(
        description="下一步行动，必须是以下三种之一：'continue'、'replan'、'respond'"
    )
    new_steps: List[str] = Field(
        default_factory=list,
        description="新的步骤列表（action 为 'replan' 时使用）"
    )


prompt_registry.register_output_schema("ops_replanner", Act.model_json_schema())
prompt_registry.register_output_schema("ops_report", Response.model_json_schema())


replanner_prompt = ChatPromptTemplate.from_messages(
    [("system", prompt_registry.get("ops_replanner").content), ("placeholder", "{messages}")]
)

response_prompt = ChatPromptTemplate.from_messages(
    [("system", prompt_registry.get("ops_report").content), ("placeholder", "{messages}")]
)


async def replanner(state: PlanExecuteState) -> Dict[str, Any]:
    """重新规划节点：决定是继续、调整计划还是生成最终报告"""
    logger.info("=== Replanner：决策下一步行动 ===")

    input_text = state.get("input", "")
    plan = state.get("plan", [])
    past_steps = state.get("past_steps", [])
    replan_count = state.get("replan_count", 0)

    logger.info(f"剩余计划步骤: {len(plan)}")
    logger.info(f"已执行步骤: {len(past_steps)}")
    logger.info(f"已 Replan 次数: {replan_count}")

    # 强制限制：超过最大步骤数直接生成响应
    MAX_STEPS = config.max_plan_steps
    if len(past_steps) >= MAX_STEPS:
        logger.warning(f"已执行 {len(past_steps)} 个步骤，超过最大限制 {MAX_STEPS}，强制生成最终报告")
        llm = create_ops_model(state)
        return await _generate_response(state, llm)

    # 获取可用工具列表
    try:
        all_tools = list(DEFAULT_LOCAL_AGENT_TOOLS)
        tools_description = format_tools_description(all_tools)
    except Exception as e:
        logger.warning(f"获取工具列表失败: {e}")
        tools_description = "无法获取工具列表"

    llm = create_ops_model(state)

    steps_summary = "\n".join([
        f"步骤: {step}\n结果: {result[:300]}..."
        for step, result in past_steps
    ])

    if plan:
        logger.info("还有剩余计划，评估下一步行动")

        replanner_chain = replanner_prompt | llm.with_structured_output(Act, method="function_calling")

        try:
            messages = [
                ("user", f"原始运营问题: {input_text}"),
                ("user", f"已执行的步骤:\n{steps_summary}"),
                ("user", f"剩余计划: {', '.join(plan)}"),
                ("user", f"⚠️ 重要提示：已执行 {len(past_steps)} 个步骤，请优先考虑信息是否已足够生成报告（respond）")
            ]

            act = await replanner_chain.ainvoke({
                "messages": messages,
                "tools_description": tools_description
            })

            if isinstance(act, Act):
                action = act.action
                new_steps = act.new_steps
            else:
                action = act.get("action", "continue")  # type: ignore
                new_steps = act.get("new_steps", [])  # type: ignore

            logger.info(f"Replanner 决策: {action}")

            if action == "respond":
                if _has_explicit_data_step(plan):
                    logger.info("剩余计划仍有明确数据工具，覆盖提前 respond 并继续执行")
                    return {}
                logger.info("决定生成最终报告")
                return await _generate_response(state, llm)

            elif action == "replan":
                # 已执行 >= 5 步或超过最大 replan 次数，禁止 replan
                if len(past_steps) >= 5 or replan_count >= config.max_replan_count:
                    logger.warning(f"超出限制，禁止 replan，强制生成报告")
                    return await _generate_response(state, llm)

                if len(new_steps) > len(plan):
                    logger.warning(f"新步骤数 {len(new_steps)} > 剩余步骤数 {len(plan)}，截断")
                    new_steps = new_steps[:len(plan)]

                logger.info(f"决定调整计划，新步骤数量: {len(new_steps)}")
                if new_steps:
                    return {"plan": [str(step)[:1000] for step in new_steps], "replan_count": replan_count + 1}
                else:
                    logger.warning("replan 但未提供新步骤，继续执行原计划")
                    return {}

            else:  # action == "continue"
                logger.info("决定继续执行当前计划")
                return {}

        except Exception as e:
            logger.error("重新规划失败: {}，继续执行剩余计划", type(e).__name__)
            return {}

    else:
        logger.info("计划已执行完毕，生成最终报告")
        return await _generate_response(state, llm)


async def _generate_response(state: PlanExecuteState, llm) -> Dict[str, Any]:
    """生成最终运营分析报告"""
    logger.info("生成最终运营分析报告...")

    input_text = state.get("input", "")
    past_steps = state.get("past_steps", [])

    execution_history = "\n\n".join([
        f"### 步骤: {step}\n**结果:**\n{result}"
        for step, result in past_steps
    ])

    response_gen = response_prompt | llm.with_structured_output(Response, method="function_calling")

    try:
        messages = [
            ("user", f"原始运营问题: {input_text}"),
            ("user", f"执行历史:\n{execution_history}"),
            ("user", "请基于以上信息生成专业的运营分析报告")
        ]

        response_obj = await response_gen.ainvoke({"messages": messages})

        if isinstance(response_obj, Response):
            final_response = response_obj.response
        else:
            final_response = response_obj.get("response", "")  # type: ignore

        final_response = sanitize_model_output(str(final_response))[:20_000]
        if not final_response.strip():
            raise ValueError("empty_report")
        logger.info(f"最终报告生成完成，长度: {len(final_response)}")
        return {"response": final_response}

    except Exception as e:
        logger.error("生成报告失败: {}", type(e).__name__)
        fallback = f"""# 运营分析结果

## 原始问题
{input_text}

## 执行步骤
{_format_simple_steps(past_steps)}

## 说明
由于系统异常，无法生成完整分析报告。以上是已收集的数据信息。
"""
        return {"response": fallback}


def _format_simple_steps(past_steps: list) -> str:
    if not past_steps:
        return "无"
    formatted = []
    for i, (step, result) in enumerate(past_steps, 1):
        result_preview = result[:200] + "..." if len(result) > 200 else result
        formatted.append(f"{i}. **{step}**\n   {result_preview}\n")
    return "\n".join(formatted)
