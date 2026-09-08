"""统一工具传输层：本地与 MCP 共享 ToolSpec，MCP 故障不静默回退。"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from loguru import logger

from app.agent.mcp_client import get_mcp_client
from app.agent.tool_registry import TOOL_SPEC_REGISTRY, tool_catalog_hash
from app.config import config


class LocalToolProvider:
    name = "local"

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        spec = TOOL_SPEC_REGISTRY.get(tool_name)
        if spec is None:
            raise RuntimeError(f"工具未注册: {tool_name}")
        return await spec.implementation.ainvoke(spec.validate_execution(arguments))

    async def health(self) -> dict[str, Any]:
        return {"transport": self.name, "status": "ready", "tools": len(TOOL_SPEC_REGISTRY)}


class MCPToolProvider:
    name = "mcp"

    def __init__(self) -> None:
        self._failures = 0
        self._open_until = 0.0
        self._tools = None
        self._lock = asyncio.Lock()

    async def _discover(self):  # type: ignore[no-untyped-def]
        if self._tools is not None:
            return self._tools
        async with self._lock:
            if self._tools is None:
                client = await asyncio.wait_for(get_mcp_client(), timeout=config.mcp_connect_timeout_seconds)
                tools = await asyncio.wait_for(client.get_tools(), timeout=config.mcp_connect_timeout_seconds)
                discovered = {tool.name: tool for tool in tools}
                missing = sorted(set(TOOL_SPEC_REGISTRY) - set(discovered))
                if missing:
                    raise RuntimeError(f"MCP Schema 不完整，缺少工具: {', '.join(missing)}")
                manifest_tool = discovered.get("tool_manifest")
                if manifest_tool is None:
                    raise RuntimeError("MCP 未提供 ToolSpec manifest")
                manifest = await manifest_tool.ainvoke({})
                if isinstance(manifest, list) and manifest:
                    block = manifest[0]
                    text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
                    if isinstance(text, str):
                        manifest = json.loads(text)
                if not isinstance(manifest, dict) or manifest.get("catalog_hash") != tool_catalog_hash():
                    raise RuntimeError("MCP ToolSpec 版本或 Schema 与本地不一致")
                self._tools = discovered
        return self._tools

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if time.monotonic() < self._open_until:
            raise RuntimeError("MCP 熔断器已打开，请稍后重试")
        if tool_name not in TOOL_SPEC_REGISTRY:
            raise RuntimeError(f"工具未注册: {tool_name}")
        try:
            tools = await self._discover()
            result = await asyncio.wait_for(
                tools[tool_name].ainvoke(arguments), timeout=config.mcp_tool_timeout_seconds,
            )
            self._failures = 0
            return result
        except Exception as exc:
            self._failures += 1
            self._tools = None
            if self._failures >= config.mcp_circuit_breaker_failures:
                self._open_until = time.monotonic() + config.mcp_circuit_breaker_seconds
            logger.warning("MCP 工具调用失败且不会回退本地: {}", type(exc).__name__)
            raise RuntimeError(f"MCP 工具 {tool_name} 调用失败") from exc

    async def health(self) -> dict[str, Any]:
        try:
            tools = await self._discover()
            return {"transport": self.name, "status": "ready", "tools": len(tools)}
        except Exception as exc:
            return {"transport": self.name, "status": "unavailable", "error": type(exc).__name__}

    def reset(self) -> None:
        self._failures = 0
        self._open_until = 0
        self._tools = None


local_tool_provider = LocalToolProvider()
mcp_tool_provider = MCPToolProvider()


def get_tool_provider():
    return mcp_tool_provider if config.agent_tool_transport == "mcp" else local_tool_provider
