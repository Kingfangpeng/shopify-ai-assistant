"""已鉴权的聊天会话、消息持久化与 SSE 接口。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.errors import AppError
from app.db.engine import db_session
from app.models.request import ChatRequest, CreateChatSessionRequest, ImportChatSessionsRequest
from app.services.chat import chat_service
from app.services.rag_agent_service import rag_agent_service

router = APIRouter()


@router.get("/chat/sessions")
async def list_sessions(limit: int = 50, offset: int = 0, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        sessions = chat_service.list_sessions(db, context.user.id, limit, offset)
        return {"items": [chat_service.serialize_session(item) for item in sessions]}


@router.post("/chat/sessions", status_code=201)
async def create_session(payload: CreateChatSessionRequest, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        session = chat_service.create_session(db, context.user.id, payload.title)
        return chat_service.serialize_session(session, include_messages=True)


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        session = chat_service.get_session(db, context.user.id, session_id, with_messages=True)
        return chat_service.serialize_session(session, include_messages=True)


@router.delete("/chat/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        chat_service.delete_session(db, context.user.id, session_id)


@router.post("/chat/sessions/import")
async def import_sessions(payload: ImportChatSessionsRequest, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        return chat_service.import_sessions(db, context.user.id, payload.sessions)


@router.post("/chat")
async def chat(request: ChatRequest, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        session = chat_service.get_session(db, context.user.id, request.session_id)
        history = chat_service.recent_context(db, context.user.id, request.session_id)
        chat_service.add_message(db, session, "user", request.question)
    try:
        answer = await rag_agent_service.query(request.question, history=history)
    except Exception as exc:
        logger.exception("RAG 对话失败")
        raise AppError("chat_failed", "生成回答失败，请稍后重试", 503) from exc
    with db_session() as db:
        session = chat_service.get_session(db, context.user.id, request.session_id)
        chat_service.add_message(db, session, "assistant", answer)
    return {"answer": answer, "session_id": request.session_id, "source": "knowledge_and_model"}


@router.post("/chat_stream")
async def chat_stream(request: ChatRequest, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        session = chat_service.get_session(db, context.user.id, request.session_id)
        history = chat_service.recent_context(db, context.user.id, request.session_id)
        chat_service.add_message(db, session, "user", request.question)

    async def event_generator():
        full_answer = ""
        failed = False
        async for chunk in rag_agent_service.query_stream(request.question, history=history):
            if chunk.get("type") == "content":
                full_answer += str(chunk.get("data") or "")
            if chunk.get("type") == "error":
                failed = True
                chunk = {"type": "error", "data": "生成回答失败，请稍后重试"}
            yield {"event": "message", "data": json.dumps(chunk, ensure_ascii=False)}
        if full_answer:
            with db_session() as db:
                session = chat_service.get_session(db, context.user.id, request.session_id)
                chat_service.add_message(db, session, "assistant", full_answer, "failed" if failed else "complete")

    return EventSourceResponse(event_generator())
