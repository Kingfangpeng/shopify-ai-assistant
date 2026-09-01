"""LLM 工厂类

使用 LangChain ChatOpenAI 通过 OpenAI 兼容模式调用各大模型
支持: OpenAI / DeepSeek / Qwen（阿里云 DashScope）及其他兼容接口
"""

from langchain_openai import ChatOpenAI
from app.config import config
from loguru import logger


class LLMFactory:
    """LLM 工厂类 - 使用 OpenAI 兼容模式"""

    @staticmethod
    def create_chat_model(
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> ChatOpenAI:
        model = model or config.llm_model
        base_url = base_url or config.llm_api_base
        api_key = api_key or config.llm_api_key

        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
        )

        logger.debug(f"创建 LLM: model={model}, base_url={base_url}")
        return llm


# 全局 LLM 工厂实例
llm_factory = LLMFactory()
