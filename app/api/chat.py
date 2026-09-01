"""对话接口

提供基于 RAG Agent 的普通对话和流式对话接口
"""

import json
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from app.models.request import ChatRequest, ClearRequest
from app.models.response import SessionInfoResponse, ApiResponse
from app.services.rag_agent_service import rag_agent_service
from loguru import logger

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """快速对话接口（RAG 知识库问答）"""
    try:
        logger.info(f"[会话 {request.id}] 收到快速对话请求: {request.question}")
        answer = await rag_agent_service.query(
            request.question,
            session_id=request.id
        )
        logger.info(f"[会话 {request.id}] 快速对话完成")
        return {
            "code": 200,
            "message": "success",
            "data": {
                "success": True,
                "answer": answer,
                "errorMessage": None
            }
        }
    except Exception as e:
        logger.error(f"对话接口错误: {e}")
        return {
            "code": 500,
            "message": "error",
            "data": {
                "success": False,
                "answer": None,
                "errorMessage": str(e)
            }
        }


@router.post("/chat_stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口（SSE）"""
    logger.info(f"[会话 {request.id}] 收到流式对话请求: {request.question}")

    async def event_generator():
        try:
            async for chunk in rag_agent_service.query_stream(request.question, session_id=request.id):
                chunk_type = chunk.get("type", "unknown")
                chunk_data = chunk.get("data", None)

                if chunk_type == "status":
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "status", "data": chunk_data}, ensure_ascii=False)
                    }
                elif chunk_type == "debug":
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "debug",
                            "node": chunk.get("node", "unknown"),
                            "message_type": chunk.get("message_type", "unknown")
                        }, ensure_ascii=False)
                    }
                elif chunk_type == "tool_call":
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "tool_call", "data": chunk_data}, ensure_ascii=False)
                    }
                elif chunk_type == "search_results":
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "search_results", "data": chunk_data}, ensure_ascii=False)
                    }
                elif chunk_type == "content":
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "content", "data": chunk_data}, ensure_ascii=False)
                    }
                elif chunk_type == "complete":
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "done", "data": chunk_data}, ensure_ascii=False)
                    }
                elif chunk_type == "error":
                    yield {
                        "event": "message",
                        "data": json.dumps({"type": "error", "data": str(chunk_data)}, ensure_ascii=False)
                    }

            logger.info(f"[会话 {request.id}] 流式对话完成")

        except Exception as e:
            logger.error(f"流式对话接口错误: {e}")
            yield {
                "event": "message",
                "data": json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())


@router.post("/chat/clear", response_model=ApiResponse)
async def clear_session(request: ClearRequest):
    """清空会话历史"""
    try:
        success = rag_agent_service.clear_session(request.session_id)
        logger.info(f"清空会话: {request.session_id}, 结果: {success}")
        return ApiResponse(
            status="success" if success else "error",
            message="会话已清空" if success else "清空会话失败",
            data=None
        )
    except Exception as e:
        logger.error(f"清空会话错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str) -> SessionInfoResponse:
    """查询会话历史"""
    try:
        history = rag_agent_service.get_session_history(session_id)
        return SessionInfoResponse(
            session_id=session_id,
            message_count=len(history),
            history=history
        )
    except Exception as e:
        logger.error(f"获取会话信息错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))
