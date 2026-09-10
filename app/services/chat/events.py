"""面向界面与历史记录的有界 Agent 活动事件。"""

from __future__ import annotations

from typing import Any

from app.services.output_safety import sanitize_model_output


TRACE_SCHEMA_VERSION = 1
TRACE_LIMIT = 80


def activity_event(
    stage: str,
    message: str,
    *,
    status: str = "complete",
    operation: str = "chain",
    **details: Any,
) -> dict[str, Any]:
    """创建不包含 Prompt、隐藏推理或原始工具输出的公开事件。"""
    event: dict[str, Any] = {
        "type": "activity",
        "schema_version": TRACE_SCHEMA_VERSION,
        "stage": stage,
        "status": status,
        "operation": operation,
        "message": message,
    }
    event.update({key: value for key, value in details.items() if value is not None})
    return sanitize_trace_event(event)


def sanitize_trace_event(event: dict[str, Any]) -> dict[str, Any]:
    """只保留前端展示所需字段，并限制单条事件大小。"""
    output: dict[str, Any] = {
        "type": sanitize_model_output(str(event.get("type") or "activity"))[:40],
        "schema_version": TRACE_SCHEMA_VERSION,
    }
    string_keys = (
        "stage", "status", "operation", "phase", "message", "model", "route",
        "strategy", "reranker_status", "decision", "current_step", "result_preview",
        "code", "timezone",
    )
    for key in string_keys:
        value = event.get(key)
        if value is not None:
            output[key] = sanitize_model_output(str(value))[:1000]
    for key in (
        "duration_ms", "candidates", "selected", "cited", "step", "revision", "dense_candidates",
        "sparse_candidates",
    ):
        value = event.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            output[key] = max(0, int(round(value)))
    for key in ("knowledge_used", "exact_identifier_match", "degraded"):
        if isinstance(event.get(key), bool):
            output[key] = event[key]
    if isinstance(event.get("files"), list):
        output["files"] = [
            sanitize_model_output(str(value))[:255]
            for value in event["files"][:5]
            if str(value).strip()
        ]
    if isinstance(event.get("plan"), list):
        output["plan"] = [sanitize_model_output(str(step))[:1000] for step in event["plan"][:12]]
    if isinstance(event.get("period"), dict):
        output["period"] = {
            key: sanitize_model_output(str(event["period"].get(key, "")))[:32]
            for key in ("from", "to")
        }
    return output


def append_trace(trace: list[dict[str, Any]], event: dict[str, Any]) -> list[dict[str, Any]]:
    return (trace + [sanitize_trace_event(event)])[-TRACE_LIMIT:]


def emit_graph_activity(event: dict[str, Any]) -> None:
    """在 LangGraph 节点内发送自定义事件；单元测试直调节点时安全跳过。"""
    try:
        from langgraph.config import get_stream_writer
        get_stream_writer()(sanitize_trace_event(event))
    except RuntimeError:
        return
