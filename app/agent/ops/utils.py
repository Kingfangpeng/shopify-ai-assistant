"""
AIOps Agent 通用工具函数
"""

from typing import List

from app.config import config
from app.core.llm_factory import llm_factory
from urllib.parse import urlparse


def selected_model(state) -> str:
    """模型由 HTTP 层校验后注入，不能由模型生成的步骤改写。"""
    return (state.get("context") or {}).get("model") or config.rag_model


def create_ops_model(state):
    model = selected_model(state)
    options = {}
    # DeepSeek 的强制结构化 function calling 在非思考模式下使用。
    if urlparse(config.llm_api_base).hostname == "api.deepseek.com" and model.startswith("deepseek-v4-"):
        options["extra_body"] = {"thinking": {"type": "disabled"}}
    return llm_factory.create_chat_model(model=model, temperature=0, streaming=False, **options)


def format_tools_description(tools: List) -> str:
    """格式化工具列表为描述文本"""
    tool_descriptions = []
    for tool in tools:
        if hasattr(tool, 'name') and hasattr(tool, 'description'):
            tool_descriptions.append(f"- {tool.name}: {tool.description}")
    return "\n".join(tool_descriptions)
