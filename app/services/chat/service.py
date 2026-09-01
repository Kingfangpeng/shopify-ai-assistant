"""SQLite 聊天仓储，强制按用户隔离会话。"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.db.models import ChatMessage, ChatSession, utcnow


class ChatService:
    def create_session(self, db: Session, user_id: str, title: str = "新对话", legacy_id: str | None = None) -> ChatSession:
        session = ChatSession(user_id=user_id, title=self._clean_title(title), legacy_id=(legacy_id or "")[:100] or None)
        db.add(session)
        db.flush()
        return session

    def list_sessions(self, db: Session, user_id: str, limit: int = 50, offset: int = 0) -> list[ChatSession]:
        return list(db.scalars(
            select(ChatSession).where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc()).offset(max(0, offset)).limit(max(1, min(limit, 100)))
        ))

    def get_session(self, db: Session, user_id: str, session_id: str, with_messages: bool = False) -> ChatSession:
        query = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        if with_messages:
            query = query.options(selectinload(ChatSession.messages))
        session = db.scalar(query)
        if not session:
            raise AppError("chat_session_not_found", "对话不存在", 404)
        return session

    def delete_session(self, db: Session, user_id: str, session_id: str) -> None:
        db.delete(self.get_session(db, user_id, session_id))

    def add_message(self, db: Session, session: ChatSession, role: str, content: str, status: str = "complete") -> ChatMessage:
        if role not in {"user", "assistant"}:
            raise ValueError("不支持的消息角色")
        cleaned = self._clean_content(content)
        next_sequence = int(db.scalar(
            select(func.coalesce(func.max(ChatMessage.sequence), 0)).where(ChatMessage.session_id == session.id)
        ) or 0) + 1
        message = ChatMessage(session_id=session.id, sequence=next_sequence, role=role, content=cleaned, status=status[:20])
        db.add(message)
        if role == "user" and session.title == "新对话":
            session.title = self._clean_title(cleaned)
        session.updated_at = utcnow()
        db.flush()
        return message

    def recent_context(self, db: Session, user_id: str, session_id: str, count: int = 12, char_limit: int = 8000) -> list[dict[str, str]]:
        self.get_session(db, user_id, session_id)
        rows = list(db.scalars(
            select(ChatMessage).where(ChatMessage.session_id == session_id, ChatMessage.status == "complete")
            .order_by(ChatMessage.sequence.desc()).limit(max(1, min(count, 12)))
        ))
        result: list[dict[str, str]] = []
        used = 0
        for row in reversed(rows):
            remaining = char_limit - used
            if remaining <= 0:
                break
            content = row.content[-remaining:]
            result.append({"role": row.role, "content": content})
            used += len(content)
        return result

    def import_sessions(self, db: Session, user_id: str, sessions: Iterable[dict]) -> dict[str, int]:
        imported = skipped = 0
        for item in list(sessions)[:100]:
            legacy_id = str(item.get("id") or item.get("session_id") or "")[:100]
            if legacy_id and db.scalar(select(ChatSession.id).where(ChatSession.user_id == user_id, ChatSession.legacy_id == legacy_id)):
                skipped += 1
                continue
            messages = item.get("messages") or item.get("history") or []
            if not isinstance(messages, list):
                skipped += 1
                continue
            session = self.create_session(db, user_id, str(item.get("title") or "导入的对话"), legacy_id)
            for raw in messages[:500]:
                if not isinstance(raw, dict):
                    continue
                role = str(raw.get("role") or raw.get("type") or "")
                if role == "ai":
                    role = "assistant"
                content = raw.get("content") or raw.get("text")
                if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                    self.add_message(db, session, role, content)
            imported += 1
        return {"imported": imported, "skipped": skipped}

    @staticmethod
    def serialize_session(session: ChatSession, include_messages: bool = False) -> dict:
        payload = {
            "id": session.id,
            "title": session.title,
            "created_at": session.created_at.isoformat() + "Z",
            "updated_at": session.updated_at.isoformat() + "Z",
        }
        if include_messages:
            payload["messages"] = [
                {"id": message.id, "role": message.role, "content": message.content, "status": message.status,
                 "created_at": message.created_at.isoformat() + "Z"}
                for message in session.messages
            ]
        return payload

    @staticmethod
    def _clean_title(value: str) -> str:
        clean = " ".join(value.replace("\x00", "").split())
        return clean[:120] or "新对话"

    @staticmethod
    def _clean_content(value: str) -> str:
        clean = "".join(char for char in value if char in "\n\t" or ord(char) >= 32).strip()
        if not clean:
            raise AppError("empty_message", "消息内容不能为空", 422)
        if len(clean) > 20_000:
            raise AppError("message_too_long", "消息内容不能超过 20000 个字符", 422)
        return clean


chat_service = ChatService()
