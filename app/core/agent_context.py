"""异步 Agent 运行时的服务端上下文；该值不会暴露给模型参数。"""

from contextvars import ContextVar


current_agent_user_id: ContextVar[str | None] = ContextVar("current_agent_user_id", default=None)
