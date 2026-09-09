from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import config
from app.core.errors import AppError
from app.core.llm_factory import llm_factory
from app.db.engine import db_session
from app.db.models import ChatSession, MemoryFact, User, utcnow
from app.services.chat import chat_service
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


@pytest.mark.asyncio
async def test_long_conversation_is_summarized_and_old_turns_are_not_duplicated(monkeypatch):
    user_id = _user("summary_user")
    session_id = _session(user_id)
    with db_session() as db:
        session = chat_service.get_session(db, user_id, session_id)
        chat_service.add_message(db, session, "user", "第一条旧问题")
        chat_service.add_message(db, session, "assistant", "第一条旧回答")

    class FakeModel:
        def with_structured_output(self, schema, *, method):
            assert method == "function_calling"

            class Chain:
                async def ainvoke(self, _messages):
                    return schema(summary="用户询问过第一条问题，助手已回答。")

            return Chain()

    monkeypatch.setattr(config, "conversation_summary_message_threshold", 2)
    monkeypatch.setattr(config, "conversation_summary_char_threshold", 100_000)
    monkeypatch.setattr(config, "conversation_summary_timeout_seconds", 1.0)
    monkeypatch.setattr(llm_factory, "create_chat_model", lambda **_kwargs: FakeModel())

    await memory_service.maybe_refresh_summary(user_id, session_id, "local-test")

    with db_session() as db:
        session = chat_service.get_session(db, user_id, session_id)
        assert session.summary_version == 1
        assert session.summary_through_sequence == 2
        assert chat_service.recent_context(db, user_id, session_id) == []
        history = memory_service.context_history(db, user_id, session_id, [])
        assert "第一条问题" in history[0]["content"]


def test_recent_context_prioritizes_latest_unsummarized_turn():
    user_id = _user("recent_user")
    session_id = _session(user_id)
    with db_session() as db:
        session = chat_service.get_session(db, user_id, session_id)
        chat_service.add_message(db, session, "user", "已经进入摘要的问题")
        chat_service.add_message(db, session, "assistant", "已经进入摘要的回答")
        session.summary = "较早对话摘要"
        session.summary_through_sequence = 2
        chat_service.add_message(db, session, "user", "first-new")
        chat_service.add_message(db, session, "assistant", "latest")

    with db_session() as db:
        recent = chat_service.recent_context(db, user_id, session_id, char_limit=6)
        assert recent == [{"role": "assistant", "content": "latest"}]
        history = memory_service.context_history(db, user_id, session_id, recent)
        assert "较早对话摘要" in history[0]["content"]
        assert history[-1] == {"role": "assistant", "content": "latest"}
