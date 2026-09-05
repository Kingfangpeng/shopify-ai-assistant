"""运营 Agent 数据模型"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from uuid import uuid4


class OpsRequest(BaseModel):
    """运营分析请求"""

    id: str = Field(default_factory=lambda: str(uuid4()), description="请求 ID")
    question: str = Field(..., min_length=1, max_length=20_000, description="运营问题")
    date_from: Optional[str] = Field(None, description="分析起始日期 YYYY-MM-DD")
    date_to: Optional[str] = Field(None, description="分析结束日期 YYYY-MM-DD")
    extra_context: Optional[dict] = Field(None, description="额外上下文，如 {'target_roas': 3.5}")
    session_id: str | None = Field(None, min_length=36, max_length=36, description="已有会话 ID；省略则创建新会话")
    model: str | None = Field(None, min_length=1, max_length=200, description="服务端允许的模型 ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "最近 7 天退款率上升，请结合订单与产品数据给出建议",
                "date_from": "2026-08-01",
                "date_to": "2026-08-07",
            }
        }
    )


class OpsAnalysisResponse(BaseModel):
    """运营分析响应"""

    id: str
    question: str
    plan: List[str] = Field(default_factory=list, description="执行计划步骤")
    steps: List[dict] = Field(default_factory=list, description="已执行步骤及结果")
    response: str = Field(default="", description="最终运营分析报告（Markdown）")
