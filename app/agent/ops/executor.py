"""
Executor 节点：执行单个运营分析步骤
"""

from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from loguru import logger

from app.config import config
from app.core.llm_factory import llm_factory
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time
from app.agent.mcp_client import get_mcp_client_with_retry
from .state import PlanExecuteState


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
        # 获取所有可用工具
        local_tools = [retrieve_knowledge, get_current_time]
        mcp_client = await get_mcp_client_with_retry()
        mcp_tools = await mcp_client.get_tools()
        all_tools = local_tools + mcp_tools
        logger.info(f"可用工具数量: 本地 {len(local_tools)} + MCP {len(mcp_tools)}")

        llm = llm_factory.create_chat_model(
            model=config.rag_model,
            temperature=0,
            streaming=False,
        )
        llm_with_tools = llm.bind_tools(all_tools)
        tool_node = ToolNode(all_tools)

        messages = [
            SystemMessage(content="""你是 Shopify 独立站运营数据执行引擎。

你的职责是执行具体的分析步骤，获取真实数据。对于每个步骤：
1. 理解步骤目标
2. 选择最合适的工具并调用（优先使用步骤中指定的工具）
3. 从返回数据中提取关键指标（数字、趋势、异常值）
4. 用 2~3 句话总结发现，聚焦于运营决策价值

**数字表述规范：**
- ROAS 保留一位小数（如 3.2x）
- 金额统一用 USD，保留两位小数
- 百分比变化标注方向（↑12% / ↓8%）
- 时间范围必须明确（如"过去 7 天"）

注意：
- 不要编造数据，只返回工具实际获取的信息
- 如果工具调用失败，说明失败原因并给出推断
- 专注于当前步骤，不要考虑其他任务"""),
            HumanMessage(content=f"请执行以下运营分析步骤: {task}")
        ]

        # 第一步：LLM 决定是否调用工具
        llm_response = await llm_with_tools.ainvoke(messages)
        logger.info(f"LLM 响应类型: {type(llm_response)}")

        # 第二步：如果有工具调用，执行工具
        if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
            logger.info(f"检测到 {len(llm_response.tool_calls)} 个工具调用")
            messages.append(llm_response)
            tool_messages = await tool_node.ainvoke({"messages": messages})
            messages.extend(tool_messages["messages"])
            final_response = await llm_with_tools.ainvoke(messages)
            result = final_response.content if hasattr(final_response, 'content') else str(final_response)
        else:
            logger.info("LLM 未调用工具，直接返回结果")
            result = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)

        logger.info(f"步骤执行完成，结果长度: {len(result)}")

        return {
            "plan": plan[1:],
            "past_steps": [(task, result)],
        }

    except Exception as e:
        logger.error(f"执行步骤失败: {e}", exc_info=True)
        return {
            "plan": plan[1:],
            "past_steps": [(task, f"执行失败: {str(e)}")],
        }
