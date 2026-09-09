"""语义优先规划：模型理解意图，严格结构与允许列表决定能否执行。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from loguru import logger
from openai import AuthenticationError, PermissionDeniedError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import config
from app.core.llm_factory import llm_factory
from app.agent.tool_registry import TOOL_SPEC_REGISTRY, planner_catalog
from app.prompts import prompt_registry


class ToolCallCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class RoutingDecision(BaseModel):
    """只接受完整、互相一致的计划；空工具不是规划失败。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    route: Literal["shopify", "knowledge", "mixed", "chat", "clarify", "unsupported"]
    tools: list[str] = Field(default_factory=list, max_length=4, description="旧模型兼容字段；新输出使用 tool_calls")
    tool_calls: list[ToolCallCandidate] = Field(default_factory=list, max_length=4)
    requires_analysis: bool
    reason: str = Field(default="", max_length=300)
    message: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def check_route(self) -> "RoutingDecision":
        selected = [call.name for call in self.tool_calls] or self.tools
        if self.tool_calls and self.tools and selected != self.tools:
            raise ValueError("tools 与 tool_calls 不一致")
        self.tools = selected
        if self.route in {"shopify", "mixed"}:
            if not selected:
                raise ValueError("数据路由必须有工具")
        elif selected:
            raise ValueError("非数据路由不得包含 Shopify 工具")
        if self.route in {"clarify", "unsupported"} and not self.message.strip():
            raise ValueError("澄清或能力不足必须给出说明")
        return self


prompt_registry.register_output_schema("routing", RoutingDecision.model_json_schema())


@dataclass(frozen=True)
class SemanticToolPlan:
    tools: tuple[str, ...]
    requires_analysis: bool
    reason: str
    planner: str
    route: str = "shopify"
    message: str = ""
    candidate_arguments: Mapping[str, dict[str, Any]] = field(default_factory=dict)


class SemanticToolPlanner:
    """使用单个计划提交工具，兼容原生 function calling 与严格 JSON 降级。"""

    timeout_seconds = config.semantic_planner_timeout_seconds
    planning_tool_name = "submit_read_only_plan"

    async def plan(
        self,
        question: str,
        model: str,
        tools: Sequence[BaseTool],
        history: list[dict[str, str]] | None = None,
    ) -> SemanticToolPlan | None:
        allowed = {tool.name for tool in tools}
        if not allowed:
            return None
        messages = self._messages(question, tools, history or [])
        schema = RoutingDecision.model_json_schema()
        schema["properties"]["tools"]["items"]["enum"] = sorted(allowed)
        schema["$defs"]["ToolCallCandidate"]["properties"]["name"]["enum"] = sorted(allowed)
        planning_tool = {
            "type": "function",
            "function": {
                "name": self.planning_tool_name,
                "description": "提交当前问题的只读意图计划，不执行任何业务接口。",
                "parameters": schema,
            },
        }
        options = {}
        # 路由是严格结构化任务。对本地 Qwen 关闭思考可降低延迟，参数仍由 Schema 把关。
        host = (urlparse(config.llm_api_base).hostname or "").lower()
        if host in {"127.0.0.1", "localhost", "::1"} and model.startswith("qwen3.5"):
            options["extra_body"] = {"reasoning_effort": "none"}
        elif host == "api.deepseek.com" and model.startswith("deepseek-v4-"):
            options["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            client = llm_factory.create_chat_model(model=model, temperature=0, streaming=False)
            bound = client.bind_tools(
                [planning_tool],
                tool_choice=self.planning_tool_name,
                **options,
            )
            response = await asyncio.wait_for(bound.ainvoke(messages), self.timeout_seconds)
            calls = getattr(response, "tool_calls", None) or []
            if calls:
                if len(calls) == 1 and calls[0].get("name") == self.planning_tool_name:
                    plan = self._validate(calls[0].get("args"), allowed, "semantic_tool_call")
                    if plan is not None:
                        return plan
            else:
                plan = self._from_json_content(getattr(response, "content", ""), allowed)
                if plan is not None:
                    return plan
        except (AuthenticationError, PermissionDeniedError):
            logger.warning("语义规划模型凭据不可用")
            return None
        except Exception as exc:
            logger.info("原生语义规划不可用，尝试 JSON: {}", type(exc).__name__)

        try:
            # 本地模型不支持工具协议时仍可提交相同结构，校验规则完全一致。
            client = llm_factory.create_chat_model(model=model, temperature=0, streaming=False)
            if options:
                client = client.bind(**options)
            repair_messages = messages + [SystemMessage(content=(
                "上一次结构化计划未通过完整 Schema 校验。这是唯一一次修复机会："
                "只修正工具名、候选参数类型或取值范围，仍需返回完整结构。"
            ))]
            response = await asyncio.wait_for(client.ainvoke(repair_messages), self.timeout_seconds)
            repaired = self._from_json_content(getattr(response, "content", ""), allowed)
            if repaired is not None:
                return repaired
            return SemanticToolPlan(
                (),
                False,
                "结构化候选参数在一次修复后仍未通过校验",
                "semantic_validation",
                "clarify",
                "请求参数未能通过安全校验，请补充明确的状态、数量或商品 ID 后重试。",
            )
        except Exception as exc:
            logger.warning("语义规划失败: {}", type(exc).__name__)
            return None

    @staticmethod
    def _messages(question: str, tools: Sequence[BaseTool], history: list[dict[str, str]]) -> list[Any]:
        catalog = planner_catalog()
        recent = [
            {"role": item["role"], "content": str(item.get("content") or "")[:1200]}
            for item in history[-8:] if item.get("role") in {"user", "assistant"}
        ]
        return [
            SystemMessage(content=prompt_registry.render("routing", tool_catalog=catalog)),
            HumanMessage(content=json.dumps({"recent_context": recent, "current_question": question[:4000]}, ensure_ascii=False)),
        ]

    @staticmethod
    def _validate(payload: Any, allowed: set[str], planner: str) -> SemanticToolPlan | None:
        try:
            decision = RoutingDecision.model_validate(payload)
        except (ValidationError, TypeError):
            return None
        if any(name not in allowed for name in decision.tools):
            return None
        arguments: dict[str, dict[str, Any]] = {}
        try:
            for call in decision.tool_calls:
                arguments[call.name] = TOOL_SPEC_REGISTRY[call.name].validate_candidates(call.arguments)
        except (KeyError, ValidationError, TypeError):
            return None
        return SemanticToolPlan(
            tuple(dict.fromkeys(decision.tools)),
            decision.requires_analysis or decision.route == "mixed" or len(decision.tools) > 1,
            decision.reason.strip() or "模型提交结构化只读计划",
            planner,
            decision.route,
            decision.message,
            arguments,
        )

    @classmethod
    def _from_json_content(cls, content: Any, allowed: set[str]) -> SemanticToolPlan | None:
        if isinstance(content, list):
            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        if not isinstance(content, str) or len(content) > 12_000:
            return None
        content = content.strip()
        fence = chr(96) * 3
        if content.startswith(fence + "json\n") and content.endswith(fence):
            content = content[8:-3].strip()
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return None
        return cls._validate(payload, allowed, "semantic_json")


semantic_tool_planner = SemanticToolPlanner()
