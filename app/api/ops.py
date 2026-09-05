"""已鉴权、可回看的运营 Agent SSE 接口。"""

import json
from contextlib import aclosing

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import AuthContext, get_auth_context
from app.models.ops import OpsRequest
from app.services.chat.ops_service import chat_ops_service
from app.services.model_catalog_service import model_catalog_service

router = APIRouter()


@router.post("/ops")
async def run_ops_analysis(request: OpsRequest, context: AuthContext = Depends(get_auth_context)):
    model = await model_catalog_service.resolve_model(request.model)
    run = chat_ops_service.prepare(context.user.id, request, model)

    async def event_generator():
        async with aclosing(chat_ops_service.stream(run)) as events:
            async for event in events:
                yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}

    return EventSourceResponse(event_generator(), ping=15, send_timeout=30)
