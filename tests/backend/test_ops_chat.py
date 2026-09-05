import asyncio
import importlib
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from sqlalchemy import create_engine, text

from app.auth.service import auth_service
from app.core.errors import AppError
from app.core.llm_factory import llm_factory
from app.db.engine import db_session
from app.db.models import User
from app.config import config
from app.integrations.shopify.dates import StoreDateRange
from app.main import app
from app.models.ops import OpsRequest
from app.services.chat.service import chat_service
from app.services.chat.ops_service import chat_ops_service
from app.services.model_catalog_service import model_catalog_service

ops = importlib.import_module("app.services.ops_agent_service")


@contextmanager
def logged_client(monkeypatch):
    with db_session() as db:
        user = auth_service.create_admin(db, "king", "correct-horse-battery")

    async def models(force=False):
        return {"models": ["test-flash", "test-pro"], "default_model": "test-pro"}

    monkeypatch.setattr(model_catalog_service, "list_models", models)
    monkeypatch.setattr(config, "rag_model", "test-pro")
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "king", "password": "correct-horse-battery"})
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        session_id = client.post("/api/chat/sessions", json={}, headers=headers).json()["id"]
        yield client, headers, session_id, user.id


def install_loop(monkeypatch):
    visits = []

    async def period(*_args, **_kwargs):
        return StoreDateRange("2026-09-01", "2026-09-03", "Asia/Shanghai", "测试周期", "2026-09-04")

    async def planner(state):
        visits.append(("planner", state["context"]["model"]))
        return {"plan": ["查询订单", "查询库存"]}

    async def executor(state):
        visits.append(("executor", state["context"]["model"]))
        return {"plan": state["plan"][1:], "past_steps": [(state["plan"][0], "测试查询结果")], "step_status": "complete"}

    async def replanner(state):
        visits.append(("replanner", state["context"]["model"]))
        if len(state["past_steps"]) == 1:
            return {"plan": ["补查退款"], "replan_count": 1}
        return {"response": "# 测试报告\n已完成两个只读步骤。"}

    monkeypatch.setattr(ops.shopify_service, "resolve_date_range", period)
    monkeypatch.setattr(ops, "planner", planner)
    monkeypatch.setattr(ops, "executor", executor)
    monkeypatch.setattr(ops, "replanner", replanner)
    monkeypatch.setattr(ops, "ops_graph", ops._build_ops_graph())
    return visits


def sse_events(response):
    return [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith("data:")]


def test_ops_loop_persists_trace_report_and_selected_model(monkeypatch):
    visits = install_loop(monkeypatch)
    with logged_client(monkeypatch) as (client, headers, session_id, _):
        response = client.post("/api/ops", headers=headers, json={
            "session_id": session_id, "model": "test-flash", "question": "分析订单和库存",
            "extra_context": {"model": "untrusted-model"},
        })
        assert response.status_code == 200
        events = sse_events(response)
        assert [event["type"] for event in events].count("step_complete") == 2
        assert next(event for event in events if event["type"] == "replan")["plan"] == ["补查退款"]
        assert events[-1]["type"] == "complete"
        assert events[-1]["model"] == "test-flash"
        history = client.get(f"/api/chat/sessions/{session_id}").json()["messages"]
        assert len(history) == 2
        assert history[-1]["content"] == events[-1]["response"]
        assert history[-1]["status"] == "complete"
        assert history[-1]["metadata"]["mode"] == "deep"
        assert any(row["type"] == "replan" for row in history[-1]["metadata"]["trace"])
        assert [visit[0] for visit in visits] == ["planner", "executor", "replanner", "executor", "replanner"]
        assert {visit[1] for visit in visits} == {"test-flash"}


def test_ops_authorization_csrf_ownership_and_model(monkeypatch):
    visits = install_loop(monkeypatch)
    with logged_client(monkeypatch) as (client, headers, session_id, _):
        assert client.post("/api/ops", json={"question": "测试"}).status_code == 403
        with db_session() as db:
            other = User(username="other", password_hash="test-only-hash")
            db.add(other)
            db.flush()
            other_id = chat_service.create_session(db, other.id).id
        assert client.post("/api/ops", headers=headers, json={"question": "测试", "session_id": other_id}).status_code == 404
        assert client.post("/api/ops", headers=headers, json={"question": "测试", "session_id": session_id, "model": "unknown"}).status_code == 422
        assert not visits
        assert client.get(f"/api/chat/sessions/{session_id}").json()["messages"] == []
        client.cookies.clear()
        assert client.post("/api/ops", json={"question": "测试"}).status_code == 401


def test_ops_without_session_creates_owned_history(monkeypatch):
    install_loop(monkeypatch)
    with logged_client(monkeypatch) as (client, headers, _, __):
        response = client.post("/api/ops", headers=headers, json={"question": "分析经营"})
        complete = sse_events(response)[-1]
        assert client.get(f"/api/chat/sessions/{complete['session_id']}").status_code == 200


def test_normal_chat_commits_before_stream_exhaustion(monkeypatch):
    from app.services.chat.agent_service import chat_agent_service
    observed = []
    with logged_client(monkeypatch) as (client, headers, session_id, user_id):
        async def answer(*_args, **_kwargs):
            yield {"type": "content", "data": "普通回答"}
            yield {"type": "complete", "data": {"answer": "普通回答"}}
            with db_session() as db:
                messages = chat_service.get_session(db, user_id, session_id, True).messages
                observed.append(messages[-1].role == "assistant")
        monkeypatch.setattr(chat_agent_service, "query_stream", answer)
        response = client.post("/api/chat_stream", headers=headers, json={"question": "测试", "session_id": session_id})
        assert response.status_code == 200
        assert observed == [True]


def test_continue_with_empty_graph_update_executes_remaining_steps(monkeypatch):
    install_loop(monkeypatch)

    async def continue_then_report(state):
        return {} if state["plan"] else {"response": "完成剩余步骤"}

    monkeypatch.setattr(ops, "replanner", continue_then_report)
    monkeypatch.setattr(ops, "ops_graph", ops._build_ops_graph())
    with logged_client(monkeypatch) as (client, headers, session_id, _):
        response = client.post("/api/ops", headers=headers, json={"question": "分析", "session_id": session_id})
        events = sse_events(response)
        assert events[-1]["type"] == "complete"
        assert sum(event["type"] == "step_complete" for event in events) == 2


def make_run():
    with db_session() as db:
        user = auth_service.create_admin(db, "king", "correct-horse-battery")
        session = chat_service.create_session(db, user.id)
    return chat_ops_service.prepare(user.id, OpsRequest(question="分析经营", session_id=session.id), "test-flash")


def saved_answer(run):
    with db_session() as db:
        session = chat_service.get_session(db, run.user_id, run.request.session_id, True)
        return chat_service.serialize_session(session, True)["messages"][-1]


@pytest.mark.asyncio
async def test_cancellation_closes_graph_and_saves_interrupted_message(monkeypatch):
    run = make_run()
    closed = []

    async def diagnose(*_args, **_kwargs):
        try:
            yield {"type": "plan", "plan": ["读取订单"]}
            await asyncio.sleep(3600)
        finally:
            closed.append(True)

    monkeypatch.setattr(ops.ops_agent_service, "diagnose", diagnose)
    events = chat_ops_service.stream(run)
    assert (await anext(events))["type"] == "plan"
    task = asyncio.create_task(anext(events))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == [True]
    assert saved_answer(run)["status"] == "interrupted"
    assert saved_answer(run)["metadata"]["trace"][0]["plan"] == ["读取订单"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "disconnect", "empty_report"])
async def test_failures_never_save_a_successful_report(monkeypatch, failure):
    run = make_run()

    async def diagnose(*_args, **_kwargs):
        yield {"type": "plan", "plan": ["读取订单"]}
        if failure == "exception":
            raise RuntimeError("private-provider-secret")
        if failure == "empty_report":
            yield {"type": "complete", "response": ""}

    monkeypatch.setattr(ops.ops_agent_service, "diagnose", diagnose)
    events = [event async for event in chat_ops_service.stream(run)]
    assert events[-1]["type"] == "error"
    assert saved_answer(run)["status"] == "failed"
    assert "private-provider-secret" not in json.dumps(saved_answer(run))


@pytest.mark.asyncio
async def test_deleted_session_is_not_recreated_by_stream(monkeypatch):
    run = make_run()

    async def diagnose(*_args, **_kwargs):
        yield {"type": "plan", "plan": ["查询"]}

    monkeypatch.setattr(ops.ops_agent_service, "diagnose", diagnose)
    stream = chat_ops_service.stream(run)
    await anext(stream)
    with db_session() as db:
        chat_service.delete_session(db, run.user_id, run.request.session_id)
    await stream.aclose()
    with db_session() as db:
        with pytest.raises(AppError):
            chat_service.get_session(db, run.user_id, run.request.session_id)


@pytest.mark.asyncio
async def test_ops_timeout_emits_failure(monkeypatch):
    async def stalled(*_args, **_kwargs):
        await asyncio.sleep(3600)

    monkeypatch.setattr(ops.shopify_service, "resolve_date_range", stalled)
    monkeypatch.setattr(ops.ops_agent_service, "timeout_seconds", 0.01)
    events = [event async for event in ops.ops_agent_service.diagnose(OpsRequest(question="测试"))]
    assert events[-1]["code"] == "ops_timeout"


@pytest.mark.asyncio
async def test_all_real_nodes_construct_the_requested_model(monkeypatch):
    planner_module = importlib.import_module("app.agent.ops.planner")
    executor_module = importlib.import_module("app.agent.ops.executor")
    replanner_module = importlib.import_module("app.agent.ops.replanner")
    used = []

    class FakeModel:
        def with_structured_output(self, schema, *, method):
            assert method == "function_calling"
            async def response(_input):
                if schema.__name__ == "Plan":
                    return schema(steps=["独立测试步骤"])
                if schema.__name__ == "Act":
                    return schema(action="respond")
                return schema(response="测试报告")
            return RunnableLambda(response)

        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(content="无调用")

    def model(**kwargs):
        used.append(kwargs["model"])
        return FakeModel()

    monkeypatch.setattr(llm_factory, "create_chat_model", model)
    monkeypatch.setattr(planner_module, "retrieve_knowledge", SimpleNamespace(ainvoke=AsyncMock(return_value="")))
    state = {"input": "测试", "context": {"model": "selected-flash"}, "plan": ["独立测试步骤"],
             "past_steps": [("之前步骤", "结果")], "replan_count": 0, "response": ""}
    await planner_module.planner(state)
    await executor_module.executor(state)
    await replanner_module.replanner(state)
    assert used == ["selected-flash"] * 3


def test_incremental_migration_preserves_legacy_messages(tmp_path):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib.util
    from pathlib import Path

    migration_path = Path(__file__).parents[2] / "alembic/versions/20260904_0002_chat_details.py"
    spec = importlib.util.spec_from_file_location("chat_details_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, content TEXT)"))
        connection.execute(text("INSERT INTO chat_messages VALUES (1, 'old message')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        assert connection.execute(text("SELECT content, details_json FROM chat_messages")).one() == ("old message", "{}")
    engine.dispose()


def test_migration_chain_has_one_head_and_preserves_prior_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["20260904_0002"]
    assert script.get_revision("20260904_0002").down_revision == "20260901_0002"


@pytest.mark.asyncio
async def test_provider_json_error_does_not_break_planner_error_handling(monkeypatch):
    module = importlib.import_module("app.agent.ops.planner")

    class UnsupportedModel:
        def with_structured_output(self, _schema, **_kwargs):
            async def fail(_input):
                raise RuntimeError("{'error': {'message': 'response_format unavailable'}}")
            return RunnableLambda(fail)

    monkeypatch.setattr(module, "create_ops_model", lambda _state: UnsupportedModel())
    monkeypatch.setattr(module, "retrieve_knowledge", SimpleNamespace(ainvoke=AsyncMock(return_value="")))
    result = await module.planner({"input": "测试", "context": {}})
    assert result["plan"]


def test_deepseek_compatibility_is_scoped_to_ops_and_official_provider(monkeypatch):
    from app.agent.ops.utils import create_ops_model
    calls = []
    monkeypatch.setattr(llm_factory, "create_chat_model", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(config, "llm_api_base", "https://api.deepseek.com/v1")
    create_ops_model({"context": {"model": "deepseek-v4-flash"}})
    assert calls[-1]["extra_body"] == {"thinking": {"type": "disabled"}}
    monkeypatch.setattr(config, "llm_api_base", "http://localhost:11434/v1")
    create_ops_model({"context": {"model": "local-model"}})
    assert "extra_body" not in calls[-1]
