"""Pydantic 请求模型"""

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID", min_length=36, max_length=36)
    question: str = Field(..., description="用户问题", min_length=1, max_length=20_000)
    model: str | None = Field(default=None, description="服务端允许的模型 ID", min_length=1, max_length=200)


class ClearRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    session_id: str = Field(..., description="会话 ID", alias="sessionId")


class CreateChatSessionRequest(BaseModel):
    title: str = Field(default="新对话", max_length=120)


class ImportChatSessionsRequest(BaseModel):
    sessions: list[dict] = Field(default_factory=list, max_length=100)
