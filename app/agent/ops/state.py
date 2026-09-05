"""
Plan-Execute-Replan 状态定义 - Shopify 运营场景
"""

from typing import List, Tuple, TypedDict, Annotated, Optional, Dict, Any
import operator


class PlanExecuteState(TypedDict):
    """Plan-Execute-Replan 状态"""

    # 用户输入（运营问题描述）
    input: str

    # 执行计划（步骤列表）
    plan: List[str]

    # 已执行的步骤历史（追加式更新）
    past_steps: Annotated[List[Tuple[str, str]], operator.add]

    # 最终响应/报告
    response: str

    # 附加上下文（时间范围、店铺信息等）
    context: Optional[Dict[str, Any]]

    # Replan 次数计数（用于熔断）
    replan_count: int
    step_status: str
