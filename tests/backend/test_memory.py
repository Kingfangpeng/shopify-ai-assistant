from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import config
from app.core.errors import AppError
from app.core.llm_factory import llm_factory
from app.db.engine import db_session
from app.db.models import ChatSession, MemoryFact, User, utcnow
from app.services.memory import memory_service


def _user(username: str) -> str:
    with db_session() as db:
        row = User(username=username, password_hash="test")
        db.add(row)
        db.flush()
        return row.id


def _session(user_id: str) -> str:
    with db_session() as db:
        row = ChatSession(user_id=user_id, title="测试")
        db.add(row)
        db.flush()
        return row.id


def test_candidate_requires_approval_and_context_is_user_isolated():
    first = _user("first_user")
    second = _user("second_user")
    session_id = _session(first)
    with db_session() as db:
        candidate = memory_service.create(
            db,
            first,
            memory_key="preferred_currency",
            kind="preference",
            value="人民币",
            confidence=0.92,
        )
        assert candidate is not None
        candidate_id = candidate.id
        assert memory_service.active_context(db, first) == ""

    with db_session() as db:
        memory_service.approve(db, first, candidate_id)
        context = memory_service.context_history(db, first, session_id, [])
        assert "preferred_currency" in context[0]["content"]
        assert memory_service.active_context(db, second) == ""


def test_approving_conflict_versions_and_supersedes_previous_memory():
    user_id = _user("version_user")
    with db_session() as db:
        current = memory_service.create(
            db, user_id, memory_key="report_tone", kind="preference", value="简洁", status="active"
        )
        candidate = memory_service.create(
            db, user_id, memory_key="report_tone", kind="preference", value="详细"
        )
        assert current is not None and candidate is not None
        candidate_id = candidate.id
        current_id = current.id

    with db_session() as db:
        approved = memory_service.approve(db, user_id, candidate_id)
        previous = db.get(MemoryFact, current_id)
        assert approved.status == "active"
        assert approved.version == 2
        assert approved.supersedes_id == current_id
        assert previous is not None and previous.status == "superseded"


def test_secret_and_payment_data_never_become_memory():
    user_id = _user("secret_user")
    with db_session() as db:
        assert memory_service.create(
            db,
            user_id,
            memory_key="api_key",
            kind="shop_context",
            value="sk-example123456789",
        ) is None
        with pytest.raises(AppError, match="凭据"):
            memory_service.create(
                db,
                user_id,
                memory_key="payment_note",
                kind="preference",
                value="卡号 6222 0200 0000 0000",
                status="active",
            )


def test_expired_memory_is_removed_from_context():
    user_id = _user("expiry_user")
    with db_session() as db:
        row = memory_service.create(
            db,
            user_id,
            memory_key="temporary_goal",
            kind="goal",
            value="今天完成报告",
            status="active",
            expires_at=utcnow() - timedelta(seconds=1),
        )
        assert row is not None
        assert memory_service.active_context(db, user_id) == ""
        assert db.scalar(select(MemoryFact.status).where(MemoryFact.id == row.id)) == "expired"


def test_local_llm_mode_blocks_deepseek_and_other_external_hosts(monkeypatch):
    monkeypatch.setattr(config, "local_llm_only", True)
    with pytest.raises(AppError) as error:
        llm_factory.create_chat_model(base_url="https://api.deepseek.com/v1", api_key="unused")
    assert error.value.code == "external_llm_blocked"


def test_local_llm_mode_allows_ollama_loopback(monkeypatch):
    monkeypatch.setattr(config, "local_llm_only", True)
    model = llm_factory.create_chat_model(base_url="http://127.0.0.1:11434/v1", api_key="local")
    assert str(model.openai_api_base).startswith("http://127.0.0.1:11434")
