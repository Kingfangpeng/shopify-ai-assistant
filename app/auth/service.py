"""Administrator and opaque server-side session service."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password, new_session_token, token_digest, verify_password
from app.config import config
from app.core.errors import AppError
from app.db.models import AuditEvent, AuthSession, User, utcnow


class LoginLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = utcnow()
        cutoff = now - timedelta(minutes=config.login_window_minutes)
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] < cutoff:
                attempts.popleft()
            if len(attempts) >= config.login_max_attempts:
                raise AppError("login_rate_limited", "登录尝试过多，请稍后再试", 429)

    def fail(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(utcnow())

    def success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_limiter = LoginLimiter()


class AuthService:
    @staticmethod
    def create_admin(db: Session, username: str, password: str) -> User:
        username = username.strip().lower()
        if not 3 <= len(username) <= 64 or not username.replace("_", "").replace("-", "").isalnum():
            raise ValueError("用户名必须为 3-64 位字母、数字、下划线或连字符")
        if len(password) < 12:
            raise ValueError("密码至少需要 12 个字符")
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            raise ValueError("管理员已存在，请使用 reset-password")
        user = User(username=username, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        AuthService.audit(db, user.id, "admin_created", "user", user.id)
        return user

    @staticmethod
    def reset_password(db: Session, username: str, password: str) -> None:
        if len(password) < 12:
            raise ValueError("密码至少需要 12 个字符")
        user = db.scalar(select(User).where(User.username == username.strip().lower()))
        if not user:
            raise ValueError("管理员不存在")
        user.password_hash = hash_password(password)
        user.password_changed_at = utcnow()
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
        AuthService.audit(db, user.id, "password_reset", "user", user.id)

    @staticmethod
    def login(db: Session, username: str, password: str, client_key: str, user_agent: str = "") -> tuple[User, str]:
        normalized = username.strip().lower()
        limiter_key = f"{client_key}:{normalized}"
        login_limiter.check(limiter_key)
        user = db.scalar(select(User).where(User.username == normalized))
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            login_limiter.fail(limiter_key)
            AuthService.audit(db, user.id if user else None, "login_failed", "user", user.id if user else None)
            # 失败登录也必须留下审计证据；随后抛出的鉴权错误不应回滚该记录。
            db.commit()
            raise AppError("invalid_credentials", "用户名或密码错误", 401)
        login_limiter.success(limiter_key)
        raw_token = new_session_token()
        now = utcnow()
        db.add(AuthSession(
            token_hash=token_digest(raw_token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=config.auth_session_hours),
            user_agent=user_agent[:255],
        ))
        AuthService.audit(db, user.id, "login_success", "user", user.id)
        return user, raw_token

    @staticmethod
    def validate_session(db: Session, raw_token: str) -> tuple[User, AuthSession]:
        now = utcnow()
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw_token)))
        if not session or session.revoked_at or session.expires_at <= now:
            raise AppError("authentication_required", "登录已失效，请重新登录", 401)
        if session.last_seen_at <= now - timedelta(minutes=config.auth_idle_minutes):
            session.revoked_at = now
            raise AppError("session_idle_timeout", "登录因长时间未操作而失效", 401)
        user = db.get(User, session.user_id)
        if not user or not user.is_active:
            raise AppError("authentication_required", "管理员账号不可用", 401)
        if session.last_seen_at <= now - timedelta(minutes=5):
            session.last_seen_at = now
        return user, session

    @staticmethod
    def logout(db: Session, raw_token: str, user_id: str | None = None) -> None:
        session = db.get(AuthSession, token_digest(raw_token))
        if session and not session.revoked_at:
            session.revoked_at = utcnow()
        AuthService.audit(db, user_id, "logout", "auth_session", None)

    @staticmethod
    def cleanup_sessions(db: Session) -> int:
        result = db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
        return int(result.rowcount or 0)

    @staticmethod
    def audit(
        db: Session,
        user_id: str | None,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        safe_detail = json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":"))[:2000]
        db.add(AuditEvent(
            user_id=user_id,
            action=action[:80],
            resource_type=(resource_type or "")[:40] or None,
            resource_id=(resource_id or "")[:100] or None,
            detail_json=safe_detail,
        ))


auth_service = AuthService()
