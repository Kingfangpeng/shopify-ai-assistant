"""RAG chat service.

The normal chat path uses explicit retrieval plus one direct model call.
"""

from datetime import datetime
from typing import Any, AsyncGenerator, Dict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from app.config import config
from app.core.llm_factory import llm_factory
from app.services.vector_store_manager import vector_store_manager
from app.tools.knowledge_tool import format_docs


class RagAgentService:
    """RAG chat service backed by the configured OpenAI-compatible model."""

    def __init__(self, streaming: bool = True):
        self.model_name = config.rag_model
        self.streaming = streaming
        self.system_prompt = self._build_system_prompt()
        self.model = llm_factory.create_chat_model(
            model=self.model_name,
            temperature=0.7,
            streaming=streaming,
        )
        self._history: dict[str, list[dict[str, str]]] = {}
        logger.info(f"RAG service initialized, model={self.model_name}, streaming={streaming}")

    def _build_system_prompt(self) -> str:
        return (
            "你是 Shopify 独立站运营助手。优先基于知识库资料（产品手册、广告话术、竞品分析、运营策略）回答；"
            "资料不足时要明确说明，并可给出通用建议。回答要直接、结构清晰，适合欧美电商场景。"
        )

    def _build_rag_messages(self, question: str) -> list[BaseMessage]:
        try:
            docs = vector_store_manager.similarity_search(question, k=config.rag_top_k)
            context = format_docs(docs) if docs else "知识库中没有检索到相关资料。"
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed, answering without context: {e}")
            context = f"知识库检索失败：{e}"

        user_prompt = (
            "请基于下面的知识库资料回答用户问题。"
            "如果资料不足，可以说明并给出通用运营建议。\n\n"
            f"知识库资料：\n{context}\n\n"
            f"用户问题：{question}"
        )
        return [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt),
        ]

    def _append_history(self, session_id: str, role: str, content: str) -> None:
        self._history.setdefault(session_id, []).append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
        )

    async def query(self, question: str, session_id: str) -> str:
        try:
            logger.info(f"[session {session_id}] RAG query: {question}")
            messages = self._build_rag_messages(question)
            result = await self.model.ainvoke(messages)
            answer = result.content if hasattr(result, "content") else str(result)
            self._append_history(session_id, "user", question)
            self._append_history(session_id, "assistant", answer)
            return answer
        except Exception as e:
            logger.error(f"[session {session_id}] RAG query failed: {e}")
            raise

    async def query_stream(
        self,
        question: str,
        session_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        full_answer = ""
        try:
            logger.info(f"[session {session_id}] RAG stream query: {question}")

            # 状态1：正在检索知识库
            yield {"type": "status", "data": "正在检索知识库..."}

            messages = self._build_rag_messages(question)

            # 状态2：开始生成回答
            yield {"type": "status", "data": "正在生成回答..."}

            async for chunk in self.model.astream(messages):
                text = getattr(chunk, "content", "") or ""
                if text:
                    full_answer += text
                    yield {"type": "content", "data": text, "node": "llm"}

            self._append_history(session_id, "user", question)
            self._append_history(session_id, "assistant", full_answer)
            yield {"type": "complete", "data": {"answer": full_answer, "tool_calls": []}}
        except Exception as e:
            logger.error(f"[session {session_id}] RAG stream query failed: {e}")
            yield {"type": "error", "data": str(e)}

    def clear_session(self, session_id: str) -> bool:
        self._history.pop(session_id, None)
        return True

    def get_session_history(self, session_id: str) -> list[dict[str, str]]:
        return self._history.get(session_id, [])


rag_agent_service = RagAgentService()
