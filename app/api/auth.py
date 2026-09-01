"""Local administrator login endpoints."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Request, Response

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.security import csrf_token
from app.auth.service import auth_service
from app.config import config
from app.db.engine import db_session

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response):
    client_key = request.client.host if request.client else "local"
    with db_session() as db:
        user, raw_token = auth_service.login(
            db,
            payload.username,
            payload.password,
            client_key,
            request.headers.get("User-Agent", ""),
        )
    response.set_cookie(
        config.auth_cookie_name,
        raw_token,
        max_age=config.auth_session_hours * 3600,
        httponly=True,
        secure=config.auth_cookie_secure,
        samesite="strict",
        path="/",
    )
    return {"user": {"id": user.id, "username": user.username}, "csrf_token": csrf_token(raw_token)}


@router.get("/me")
async def me(context: AuthContext = Depends(get_auth_context)):
    return {
        "authenticated": True,
        "user": {"id": context.user.id, "username": context.user.username},
        "csrf_token": csrf_token(context.raw_token),
    }


@router.post("/logout", status_code=204)
async def logout(response: Response, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        auth_service.logout(db, context.raw_token, context.user.id)
    response.delete_cookie(config.auth_cookie_name, path="/")
