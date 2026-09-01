"""
Planner 节点：制定运营分析执行计划
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


class Plan(BaseModel):
    """计划的输出格式"""
    steps: List[str] = Field(
        description="完成运营分析所需的步骤列表，按顺序执行，3~6步为宜。"
    )


planner_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent("""
                你是一位专业的 Shopify 独立站运营分析师，擅长欧美市场电商运营。

                可用工具列表（制定计划时参考）：
                {tools_description}

                注意：你的职责是制定计划，实际工具调用由 Executor 负责执行。

                {experience_context}

                **分析框架（按优先级）：**
                1. 先查知识库，获取行业基准和最佳实践
                2. 获取 Shopify 订单/转化/库存数据
                3. 获取广告投放数据（ROAS/CPC/CTR）
                4. 数据交叉验证与归因分析
                5. 输出可执行的优化建议

                **常见问题分析路径：**
                - ROAS 下跌 → 广告花费结构 → 素材/受众 → 落地页转化 → 产品竞争力
                - 转化率低 → 流量质量 → 落地页体验 → 产品定价 → 结账流程
                - 库存积压 → 销量趋势 → 广告推力 → 折扣策略 → 清仓方案

                **计划要求：**
                - 步骤数量：3~6步，不要过度分析
                - 每步描述须明确：要查什么、用哪个工具、期望得到什么
                - 步骤之间有清晰的依赖关系
                - 优先使用具体数据，避免模糊表述
            """).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
)


async def planner(state: PlanExecuteState) -> Dict[str, Any]:
    """规划节点：根据运营问题生成执行计划"""
    logger.info("=== Planner：制定运营分析计划 ===")

    input_text = state.get("input", "")
    logger.info(f"运营问题: {input_text}")

    try:
        # 步骤1: 查询知识库获取相关经验
        logger.info("查询知识库，寻找相关运营经验...")
        experience_docs = ""
        try:
            context_str = await retrieve_knowledge.ainvoke({"query": input_text})
            if context_str and context_str.strip():
                experience_docs = context_str
                logger.info(f"找到相关经验文档，长度: {len(experience_docs)}")
            else:
                logger.info("未找到相关经验文档")
        except Exception as e:
            logger.warning(f"查询知识库失败: {e}")

        # 步骤2: 获取可用工具列表
        local_tools = [retrieve_knowledge]
        mcp_client = await get_mcp_client_with_retry()
        mcp_tools = await mcp_client.get_tools()
        all_tools = local_tools + mcp_tools
        logger.info(f"可用工具数量: 本地 {len(local_tools)} + MCP {len(mcp_tools)}")

        tools_description = format_tools_description(all_tools)

        # 步骤3: 格式化经验文档上下文
        if experience_docs:
            experience_context = dedent(f"""
                ## 相关运营经验

                以下是从知识库中检索到的相关经验和最佳实践，请参考这些经验制定分析计划：

                {experience_docs}

                ---
            """).strip()
        else:
            experience_context = ""

        # 步骤4: 创建 LLM 并生成计划
        llm = llm_factory.create_chat_model(
            model=config.rag_model,
            temperature=0,
            streaming=False,
        )

        planner_chain = planner_prompt | llm.with_structured_output(Plan)

        plan_result = await planner_chain.ainvoke({
            "messages": [("user", input_text)],
            "tools_description": tools_description,
            "experience_context": experience_context
        })

        if isinstance(plan_result, Plan):
            plan_steps = plan_result.steps
        else:
            plan_steps = plan_result.get("steps", [])  # type: ignore

        logger.info(f"计划已生成，共 {len(plan_steps)} 个步骤")
        for i, step in enumerate(plan_steps, 1):
            logger.info(f"  步骤{i}: {step}")

        return {"plan": plan_steps}

    except Exception as e:
        logger.error(f"生成计划失败: {e}", exc_info=True)
        return {
            "plan": [
                "使用 retrieve_knowledge 工具查询知识库，获取相关运营策略",
                "获取近期销售和广告数据",
                "综合数据分析并生成优化建议"
            ]
        }
