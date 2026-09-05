"""E2E 专用本地服务：只替换不可用的 Milvus/LLM 外部依赖。"""

from __future__ import annotations

from app.main import app
from app.agent.semantic_planner import SemanticToolPlan, semantic_tool_planner
from app.services.model_catalog_service import model_catalog_service
from app.services.rag_agent_service import rag_agent_service
from app.services.vector_store_manager import vector_store_manager

stored_documents = []


def add_documents(documents, ids=None):
    stored_documents.extend(documents)
    return ids or [f"e2e-{index}" for index, _ in enumerate(documents)]


def delete_document_version(document_id, version=None):
    before = len(stored_documents)
    stored_documents[:] = [doc for doc in stored_documents if not (
        doc.metadata.get("document_id") == document_id
        and (version is None or doc.metadata.get("version") == version)
    )]
    return before - len(stored_documents)


def list_chunks(document_id, limit=50, offset=0):
    rows = [doc for doc in stored_documents if doc.metadata.get("document_id") == document_id]
    items = [{
        "id": f"e2e-{index}",
        "document_id": document_id,
        "file_name": doc.metadata.get("file_name"),
        "content": doc.page_content,
        "content_preview": doc.page_content[:200],
        "char_count": len(doc.page_content),
        "h1": doc.metadata.get("h1", ""),
        "h2": doc.metadata.get("h2", ""),
    } for index, doc in enumerate(rows[offset:offset + limit])]
    return {"items": items, "limit": limit, "offset": offset, "has_more": False}


async def query_stream(question, history, model=None, use_knowledge=True):
    yield {"type": "status", "data": "正在检索知识库…"}
    answer = f"已结合本地产品资料回答：{question}。当前会话包含 {len(history)} 条历史消息。"
    yield {"type": "content", "data": answer}
    yield {"type": "complete", "data": {"answer": answer, "source": "knowledge_and_model", "model": model}}


async def list_models(force=False):
    return {
        "models": ["e2e-fast", "e2e-accurate"],
        "default_model": "e2e-fast",
        "provider": "local-e2e",
        "configured": True,
        "source": "provider",
        "warning": None,
    }


vector_store_manager.add_documents = add_documents
vector_store_manager.delete_document_version = delete_document_version
vector_store_manager.list_chunks = list_chunks
vector_store_manager.similarity_search = lambda _query, k=3: stored_documents[:k]
rag_agent_service.query_stream = query_stream
model_catalog_service.list_models = list_models


async def semantic_plan(question, *_args, **_kwargs):
    # E2E 隔离外部模型，仅验证所选路由能真实走到工具/知识库和 SSE。
    if "今天" in question and ("几单" in question or "订单" in question):
        return SemanticToolPlan(("get_orders_summary",), False, "E2E", "semantic_tool_call")
    return SemanticToolPlan((), False, "E2E", "semantic_tool_call", "knowledge")


semantic_tool_planner.plan = semantic_plan


# 保留真实 LangGraph 与持久化，仅隔离节点的模型和远程数据调用。
import asyncio
import importlib

ops_module = importlib.import_module("app.services.ops_agent_service")


async def ops_planner(state):
    await asyncio.sleep(0.15)
    return {"plan": ["查询订单经营数据", "核对退款统计"]}


async def ops_executor(state):
    await asyncio.sleep(60 if "停止测试" in state["input"] else 0.4)
    return {"plan": state["plan"][1:], "past_steps": [(state["plan"][0], "隔离测试数据：已取得可验证的查询结果")],
            "step_status": "complete"}


async def ops_replanner(state):
    await asyncio.sleep(0.2)
    if len(state["past_steps"]) == 1:
        return {"plan": ["补充产品表现核查"], "replan_count": 1}
    return {"response": f"# 深度分析测试报告\n\n已完成两个只读步骤及一次重规划。\n\n使用模型：{state['context']['model']}。"}


ops_module.planner = ops_planner
ops_module.executor = ops_executor
ops_module.replanner = ops_replanner
ops_module.ops_graph = ops_module._build_ops_graph()
