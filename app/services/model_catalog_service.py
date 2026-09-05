"""OpenAI 兼容模型目录：服务端拉取、短时缓存和选择校验。"""

from __future__ import annotations

import asyncio
import re
from time import monotonic
from urllib.parse import urlparse

from loguru import logger
from openai import AsyncOpenAI

from app.config import config
from app.core.errors import AppError

MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class ModelCatalogService:
    cache_seconds = 300

    def __init__(self) -> None:
        self._cached: dict | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def list_models(self, force: bool = False) -> dict:
        now = monotonic()
        if not force and self._cached and now < self._expires_at:
            return dict(self._cached)

        async with self._lock:
            now = monotonic()
            if not force and self._cached and now < self._expires_at:
                return dict(self._cached)

            fallback = sorted({item for item in (config.rag_model, config.llm_model) if MODEL_ID_RE.fullmatch(item)})
            payload = {
                "models": fallback,
                "default_model": config.rag_model,
                "provider": urlparse(config.llm_api_base).hostname or "自定义兼容服务",
                "configured": bool(config.llm_api_key),
                "source": "configuration",
                "warning": None,
            }
            if not config.llm_api_key:
                payload["warning"] = "尚未配置模型 API Key"
            else:
                try:
                    discovered = await self._fetch_provider_models()
                    if discovered:
                        payload["models"] = discovered
                        payload["source"] = "provider"
                        if config.rag_model not in discovered:
                            payload["warning"] = "当前默认模型不在服务商返回的可用列表中"
                except Exception as exc:
                    logger.warning("模型目录刷新失败: {}", type(exc).__name__)
                    payload["warning"] = "暂时无法刷新服务商模型列表，已使用本地配置"

            self._cached = payload
            self._expires_at = monotonic() + self.cache_seconds
            return dict(payload)

    async def resolve_model(self, requested: str | None) -> str:
        selected = (requested or config.rag_model).strip()
        if not MODEL_ID_RE.fullmatch(selected):
            raise AppError("invalid_model", "模型 ID 格式无效", 422)
        catalog = await self.list_models()
        if selected not in catalog["models"]:
            raise AppError("model_not_available", "所选模型不可用，请刷新模型列表后重试", 422)
        return selected

    async def _fetch_provider_models(self) -> list[str]:
        client = AsyncOpenAI(
            api_key=config.llm_api_key,
            base_url=config.llm_api_base,
            timeout=10.0,
            max_retries=1,
        )
        try:
            page = await client.models.list()
            return sorted({item.id for item in page.data if MODEL_ID_RE.fullmatch(item.id)})
        finally:
            await client.close()

    def clear_cache(self) -> None:
        self._cached = None
        self._expires_at = 0.0


model_catalog_service = ModelCatalogService()
