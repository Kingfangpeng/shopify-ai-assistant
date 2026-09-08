"""用户可审核、可撤销的长期记忆接口。"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import AuthContext, get_auth_context
from app.db.engine import db_session
from app.services.memory import memory_service


router = APIRouter()


class CreateMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    memory_key: str = Field(min_length=2, max_length=80)
    kind: Literal["preference", "business_rule", "shop_context", "goal"]
    value: str = Field(min_length=1, max_length=500)
    expires_at: datetime | None = None


class ApproveMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str | None = Field(default=None, min_length=1, max_length=500)
    expires_at: datetime | None = None


class EditMemoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str = Field(min_length=1, max_length=500)
    expires_at: datetime | None = None


@router.get("/memories")
async def list_memories(
    status: str = "candidate",
    limit: int = 100,
    offset: int = 0,
    context: AuthContext = Depends(get_auth_context),
):
    with db_session() as db:
        return memory_service.list(db, context.user.id, status, limit, offset)


@router.post("/memories", status_code=201)
async def create_memory(
    payload: CreateMemoryRequest,
    context: AuthContext = Depends(get_auth_context),
):
    with db_session() as db:
        row = memory_service.create(
            db,
            context.user.id,
            memory_key=payload.memory_key,
            kind=payload.kind,
            value=payload.value,
            status="active",
            expires_at=payload.expires_at,
        )
        return memory_service.serialize(row)


@router.post("/memories/{memory_id}/approve")
async def approve_memory(
    memory_id: str,
    payload: ApproveMemoryRequest,
    context: AuthContext = Depends(get_auth_context),
):
    with db_session() as db:
        row = memory_service.approve(
            db,
            context.user.id,
            memory_id,
            value=payload.value,
            expires_at=payload.expires_at,
        )
        return memory_service.serialize(row)


@router.post("/memories/{memory_id}/reject")
async def reject_memory(memory_id: str, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        row = memory_service.reject(db, context.user.id, memory_id)
        return memory_service.serialize(row)


@router.post("/memories/{memory_id}/edit")
async def edit_memory(
    memory_id: str,
    payload: EditMemoryRequest,
    context: AuthContext = Depends(get_auth_context),
):
    with db_session() as db:
        row = memory_service.edit(
            db,
            context.user.id,
            memory_id,
            value=payload.value,
            expires_at=payload.expires_at,
        )
        return memory_service.serialize(row)


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        memory_service.delete(db, context.user.id, memory_id)
