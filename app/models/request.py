"""Pydantic 请求模型"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    id: str = Field(..., description="会话 ID", alias="Id")
    question: str = Field(..., description="用户问题", alias="Question")

    class Config:
        populate_by_name = True


class ClearRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID", alias="sessionId")

    class Config:
        populate_by_name = True
