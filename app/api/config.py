"""配置信息接口 - 返回非敏感配置，供前端设置页展示"""

from fastapi import APIRouter
from app.config import config

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
        "facebook_configured": bool(config.facebook_access_token),
        "google_configured": bool(config.google_ads_refresh_token),
        "rag_top_k": config.rag_top_k,
    }
