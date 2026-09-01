"""Pydantic 响应模型"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ChatResponse(BaseModel):
    answer: str = Field(..., description="AI 回答")
    session_id: str = Field(..., description="会话 ID")


class SessionInfoResponse(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message_count: int = Field(..., description="消息数量")
    history: List[Dict[str, str]] = Field(..., description="历史消息")


class ApiResponse(BaseModel):
    status: str
    message: str
    data: Optional[Any] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
