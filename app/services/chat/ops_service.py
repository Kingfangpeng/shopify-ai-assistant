"""深度分析与聊天会话的桥接：短事务保存进度，取消时不留下假成功。"""

from contextlib import aclosing
from dataclasses import dataclass

from loguru import logger

from app.core.errors import AppError
from app.db.engine import db_session
from app.models.ops import OpsRequest
from app.services.chat.service import chat_service
from app.services.ops_agent_service import ops_agent_service
from app.services.output_safety import sanitize_model_output


@dataclass
class AnalysisRun:
    request: OpsRequest
    user_id: str
    message_id: int
    history: list[dict[str, str]]


class ChatOpsService:
    def prepare(self, user_id: str, request: OpsRequest, model: str) -> AnalysisRun:
        with db_session() as db:
            session = (chat_service.get_session(db, user_id, request.session_id) if request.session_id
                       else chat_service.create_session(db, user_id))
            history = chat_service.recent_context(db, user_id, session.id)
            metadata = {"mode": "deep", "model": model, "trace": []}
            chat_service.add_message(db, session, "user", request.question, metadata=metadata)
            message = chat_service.add_message(db, session, "assistant", "正在准备深度分析…", "running", metadata)
            return AnalysisRun(request.model_copy(update={"session_id": session.id, "model": model}), user_id, message.id, history)

    @staticmethod
    def clean_event(event: dict) -> dict:
        # 仅保存用于界面展示的结构，不保存凭据、上下文和模型隐藏推理。
        output = {"type": event.get("type", "status")}
        for key in ("stage", "message", "current_step", "result_preview", "status", "model", "code", "timezone"):
            if key in event:
                output[key] = sanitize_model_output(str(event[key]))[:1000]
        for key in ("step", "revision"):
            if isinstance(event.get(key), int):
                output[key] = event[key]
        if isinstance(event.get("plan"), list):
            output["plan"] = [sanitize_model_output(str(step))[:1000] for step in event["plan"][:12]]
        if isinstance(event.get("period"), dict):
            output["period"] = {key: str(event["period"].get(key, ""))[:32] for key in ("from", "to")}
        return output

    async def stream(self, run: AnalysisRun):
        metadata = {"mode": "deep", "model": run.request.model, "trace": []}
        content = "正在准备深度分析…"
        terminal = False

        def save(status):
            with db_session() as db:
                chat_service.update_analysis(db, run.user_id, run.request.session_id, run.message_id,
                                             content, status, metadata)

        try:
            async with aclosing(ops_agent_service.diagnose(run.request, history=run.history)) as events:
                async for raw in events:
                    event = self.clean_event(raw)
                    kind = event["type"]
                    if kind == "report":
                        content = sanitize_model_output(str(raw.get("report") or ""))[:20_000]
                        if not content.strip():
                            raise AppError("empty_report", "分析未生成可用报告，请重试", 503)
                        event["report"] = content
                    elif kind == "complete":
                        # 必须收到报告；空完成不允许覆盖先前失败或生成假成功。
                        report = sanitize_model_output(str(raw.get("response") or ""))[:20_000]
                        if not report.strip():
                            raise AppError("empty_report", "分析未生成可用报告，请重试", 503)
                        content = report
                        event.update(response=content, source="ops", session_id=run.request.session_id,
                                     model=run.request.model, message_id=run.message_id)
                        save("complete")
                        terminal = True
                    elif kind == "error":
                        content = event.get("message") or "深度分析失败，请重试"
                        metadata["trace"] = (metadata["trace"] + [event])[-80:]
                        save("failed")
                        terminal = True
                    else:
                        metadata["trace"] = (metadata["trace"] + [event])[-80:]
                    if not terminal:
                        save("running")
                    yield event
                    if terminal:
                        return
            raise AppError("ops_stream_incomplete", "分析连接提前结束，已保留执行过程", 503)
        except Exception as exc:
            logger.warning("深度分析消息流异常: {}", type(exc).__name__)
            content = exc.message if isinstance(exc, AppError) else "深度分析暂时失败，请稍后重试"
            event = {"type": "error", "code": getattr(exc, "code", "ops_failed"), "message": content}
            metadata["trace"] = (metadata["trace"] + [event])[-80:]
            try:
                save("failed")
            except AppError:
                pass  # 用户可能已删除该会话，不得重新创建。
            terminal = True
            yield event
        finally:
            if not terminal:
                content = "分析已停止，以下为中止前已保存的执行过程。"
                try:
                    save("interrupted")
                except Exception as exc:
                    logger.warning("保存分析中断状态失败: {}", type(exc).__name__)


chat_ops_service = ChatOpsService()
