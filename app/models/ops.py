"""运营 Agent 数据模型"""

from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import uuid4


class OpsRequest(BaseModel):
    """运营分析请求"""

    id: str = Field(default_factory=lambda: str(uuid4()), description="请求 ID")
    question: str = Field(..., description="运营问题，如：最近7天ROAS为何下跌？")
    date_from: Optional[str] = Field(None, description="分析起始日期 YYYY-MM-DD")
    date_to: Optional[str] = Field(None, description="分析结束日期 YYYY-MM-DD")
    extra_context: Optional[dict] = Field(None, description="额外上下文，如 {'target_roas': 3.5}")
    session_id: str = Field(default_factory=lambda: str(uuid4()), description="会话 ID")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "最近7天ROAS从3.2跌到1.8，请分析原因并给出优化建议",
                "date_from": "2024-10-01",
                "date_to": "2024-10-07",
            }
        }


class OpsAnalysisResponse(BaseModel):
    """运营分析响应"""

    id: str
    question: str
    plan: List[str] = Field(default_factory=list, description="执行计划步骤")
    steps: List[dict] = Field(default_factory=list, description="已执行步骤及结果")
    response: str = Field(default="", description="最终运营分析报告（Markdown）")
