"""
MCP 客户端管理
提供全局单例的 MCP 客户端，避免重复初始化
"""

import asyncio
from typing import Optional, Dict, Any, List
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent
from loguru import logger


# 全局 MCP 客户端（延迟初始化）
_mcp_client: Optional[MultiServerMCPClient] = None


async def retry_interceptor(
    request: MCPToolCallRequest,
    handler,
    max_retries: int = 3,
    delay: float = 1.0,
):
    """MCP 工具调用重试拦截器

    当工具调用失败时，使用指数退避策略自动重试。
    如果所有重试都失败，返回包含错误信息的结果而不是抛出异常。
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(
                f"调用 MCP 工具: {request.name} "
                f"(服务器: {request.server_name}, 第 {attempt + 1}/{max_retries} 次尝试)"
            )
            result = await handler(request)
            logger.info(f"MCP 工具 {request.name} 调用成功")
            return result

        except Exception as e:
            last_error = e
            logger.warning(
                f"MCP 工具 {request.name} 调用失败 "
                f"(第 {attempt + 1}/{max_retries} 次): {str(e)}"
            )

            if attempt < max_retries - 1:
                wait_time = delay * (2 ** attempt)
                logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)

    error_msg = f"工具 {request.name} 在 {max_retries} 次重试后仍然失败: {str(last_error)}"
    logger.error(error_msg)
    return CallToolResult(
        content=[TextContent(type="text", text=error_msg)],
        isError=True
    )


from app.config import config

DEFAULT_MCP_SERVERS = config.mcp_servers


async def get_mcp_client(
    servers: Optional[Dict[str, Dict[str, str]]] = None,
    tool_interceptors: Optional[List] = None,
    force_new: bool = False
) -> MultiServerMCPClient:
    """获取或初始化 MCP 客户端（单例）"""
    global _mcp_client

    if force_new:
        logger.info("创建新的 MCP 客户端实例（非单例）")
        return _create_mcp_client(servers or DEFAULT_MCP_SERVERS, tool_interceptors)

    if _mcp_client is None:
        logger.info("初始化全局 MCP 客户端...")
        _mcp_client = _create_mcp_client(servers or DEFAULT_MCP_SERVERS, tool_interceptors)
        logger.info("全局 MCP 客户端初始化完成")

    return _mcp_client


async def get_mcp_client_with_retry(
    servers: Optional[Dict[str, Dict[str, str]]] = None,
    tool_interceptors: Optional[List] = None,
    force_new: bool = False
) -> MultiServerMCPClient:
    """获取或初始化带重试功能的 MCP 客户端"""
    interceptors = [retry_interceptor]
    if tool_interceptors:
        interceptors.extend(tool_interceptors)

    return await get_mcp_client(
        servers=servers,
        tool_interceptors=interceptors,
        force_new=force_new
    )


def _create_mcp_client(
    servers: Dict[str, Dict[str, str]],
    tool_interceptors: Optional[List] = None
) -> MultiServerMCPClient:
    """创建 MCP 客户端实例"""
    kwargs: Dict[str, Any] = {}
    if tool_interceptors:
        kwargs["tool_interceptors"] = tool_interceptors
    return MultiServerMCPClient(servers, **kwargs)  # type: ignore[arg-type]
