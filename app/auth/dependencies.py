"""FastAPI authentication dependencies."""

from dataclasses import dataclass

from fastapi import Request

from app.auth.service import auth_service
from app.config import config
from app.core.errors import AppError
from app.db.engine import db_session
from app.db.models import AuthSession, User


@dataclass
class AuthContext:
    user: User
    session: AuthSession
    raw_token: str


def get_auth_context(request: Request) -> AuthContext:
    token = request.cookies.get(config.auth_cookie_name, "")
    if not token:
        raise AppError("authentication_required", "请先登录", 401)
    with db_session() as db:
        user, session = auth_service.validate_session(db, token)
        db.expunge(user)
        db.expunge(session)
    return AuthContext(user=user, session=session, raw_token=token)


def get_current_user(request: Request) -> User:
    return get_auth_context(request).user
