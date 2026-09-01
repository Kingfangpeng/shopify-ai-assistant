"""配置信息接口 - 返回非敏感配置，供前端设置页展示"""

from fastapi import APIRouter
from loguru import logger
from app.config import config
from app.core.milvus_client import milvus_manager
from app.integrations.shopify.client import ShopifyError
from app.integrations.shopify.service import shopify_service

router = APIRouter()


def _shopify_configured() -> bool:
    token = (config.shopify_access_token or "").strip()
    domain = (config.shopify_store_domain or "").strip()
    return bool(
        token
        and domain
        and token not in {"shpat_your_token_here", "your-token"}
        and not token.startswith("shpat_your")
        and domain not in {"your-store.myshopify.com", "example.myshopify.com"}
    )


@router.get("/config")
async def get_config():
    """返回非敏感配置信息（不暴露任何 API Key）"""
    return {
        "app_name": config.app_name,
        "app_version": config.app_version,
        "llm_model": config.llm_model,
        "embedding_model": config.ollama_embedding_model,
        "milvus_collection": config.milvus_collection,
        "shopify_configured": _shopify_configured(),
        "shopify_domain": config.shopify_store_domain if _shopify_configured() else None,
        "ads_enabled": False,
        "shopify_api_version": config.shopify_api_version,
        "shopify_demo_mode": config.shopify_demo_mode,
        "milvus_status": "connected" if milvus_manager.health_check() else "disconnected",
        "rag_top_k": config.rag_top_k,
    }


@router.get("/shopify/status")
async def shopify_status():
    try:
        return await shopify_service.status()
    except ShopifyError as exc:
        logger.warning("Shopify 状态检查失败: {}", exc.code)
        return {
            "configured": shopify_service.configured,
            "connected": False,
            "demo_mode": config.shopify_demo_mode,
            "api_version": config.shopify_api_version,
            "domain": config.shopify_store_domain if shopify_service.configured else None,
            "scopes": [],
            "warning": "无法连接 Shopify，请检查令牌、权限或网络",
            "error_code": exc.code,
        }
