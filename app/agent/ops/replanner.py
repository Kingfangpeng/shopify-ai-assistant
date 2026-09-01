"""
Replanner 节点：重新规划或生成最终运营报告
"""

from textwrap import dedent
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from loguru import logger

from app.config import config
from app.core.llm_factory import llm_factory
from app.tools.knowledge_tool import retrieve_knowledge
from app.agent.mcp_client import get_mcp_client_with_retry
from .state import PlanExecuteState
from .utils import format_tools_description


class Response(BaseModel):
    """最终响应格式"""
    response: str = Field(description="对用户的最终运营分析报告（Markdown 格式）")


class Act(BaseModel):
    """重新规划的输出格式"""
    action: str = Field(
        description="下一步行动，必须是以下三种之一：'continue'、'replan'、'respond'"
    )
    new_steps: List[str] = Field(
        default_factory=list,
        description="新的步骤列表（action 为 'replan' 时使用）"
    )


replanner_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent("""
                作为运营分析决策引擎，根据已执行步骤决定下一步行动。

                可用工具列表：
                {tools_description}

                **三种行动（按优先级排序）：**

                **1. 'respond' - 信息充足，立即生成最终报告** 【最高优先级】
                   触发条件：
                   - 已执行步骤 >= 3 且获取了关键数据
                   - 或已执行步骤 >= 5（无论结果如何）
                   - 或当前信息完全满足分析需求
                   ⚠️ 信息"足够好"就应立即 respond，不要追求完美

                **2. 'continue' - 当前计划合理，继续执行** 【次优先级】
                   触发条件：剩余步骤能提供决策所需的关键信息

                **3. 'replan' - 当前计划有严重问题** 【最低优先级，严格限制】
                   触发条件：原计划明显错误或发现新的重要问题线索
                   限制：
                   - 已执行步骤 >= 5 时禁止 replan，只能 respond
                   - 新步骤数量不能超过当前剩余步骤数

                **决策口诀：**
                "优先结束 > 保持不变 > 调整计划"
                "数据足够就响应，不要追求完美"
            """).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
)

response_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent("""
                根据原始运营问题和已执行步骤的结果，生成一份专业的运营分析报告。

                **报告结构（必须包含）：**
                1. **核心问题判断**（一句话定性）
                2. **数据支撑**（关键指标，含对比基准或环比变化）
                3. **优先行动建议**（3~5条，按 ROI 从高到低排序）
                4. **预期改善效果**（量化，如"预计 ROAS 提升 15~25%"）

                **要求：**
                - 使用 Markdown 格式
                - 基于实际数据，不要编造
                - 建议要具体可操作，不要泛泛而谈
                - 如某步骤失败，要诚实说明并给出替代建议
                - 用数字说话（金额用 USD，比例用百分比）
            """).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
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
        llm = llm_factory.create_chat_model(model=config.rag_model, temperature=0, streaming=False)
        return await _generate_response(state, llm)

    # 获取可用工具列表
    try:
        local_tools = [retrieve_knowledge]
        mcp_client = await get_mcp_client_with_retry()
        mcp_tools = await mcp_client.get_tools()
        all_tools = local_tools + mcp_tools
        tools_description = format_tools_description(all_tools)
    except Exception as e:
        logger.warning(f"获取工具列表失败: {e}")
        tools_description = "无法获取工具列表"

    llm = llm_factory.create_chat_model(model=config.rag_model, temperature=0, streaming=False)

    steps_summary = "\n".join([
        f"步骤: {step}\n结果: {result[:300]}..."
        for step, result in past_steps
    ])

    if plan:
        logger.info("还有剩余计划，评估下一步行动")

        replanner_chain = replanner_prompt | llm.with_structured_output(Act)

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
                    return {"plan": new_steps, "replan_count": replan_count + 1}
                else:
                    logger.warning("replan 但未提供新步骤，继续执行原计划")
                    return {}

            else:  # action == "continue"
                logger.info("决定继续执行当前计划")
                return {}

        except Exception as e:
            logger.error(f"重新规划失败: {e}，继续执行剩余计划")
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

    response_gen = response_prompt | llm.with_structured_output(Response)

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

        logger.info(f"最终报告生成完成，长度: {len(final_response)}")
        return {"response": final_response}

    except Exception as e:
        logger.error(f"生成报告失败: {e}")
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
