"""配置管理模块 - Shopify AI Assistant"""

from typing import Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 应用 ────────────────────────────────────────────────────────
    app_name: str = "Shopify AI Assistant"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9901

    # ── LLM（OpenAI 兼容，支持 OpenAI / DeepSeek / Qwen）──────────
    llm_api_key: str = ""
    llm_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    rag_model: str = "gpt-4o"

    # ── Ollama 本地 Embedding ──────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    embedding_dimensions: int = 768

    # ── Milvus 向量数据库 ──────────────────────────────────────────
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_timeout: int = 10000
    milvus_collection: str = "shopify_kb"

    # ── RAG 配置 ───────────────────────────────────────────────────
    rag_top_k: int = 3
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # ── Shopify Admin API ──────────────────────────────────────────
    shopify_store_domain: str = ""
    shopify_api_version: str = "2024-10"
    shopify_access_token: str = ""
    shopify_webhook_secret: str = ""

    # ── Facebook Marketing API ─────────────────────────────────────
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    facebook_access_token: str = ""
    facebook_ad_account_id: str = ""

    # ── Google Ads API ─────────────────────────────────────────────
    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    google_ads_customer_id: str = ""

    # ── MCP Server 地址 ────────────────────────────────────────────
    mcp_shopify_transport: str = "streamable-http"
    mcp_shopify_url: str = "http://localhost:8003/mcp"
    mcp_ads_transport: str = "streamable-http"
    mcp_ads_url: str = "http://localhost:8004/mcp"

    # ── Agent 行为控制 ─────────────────────────────────────────────
    max_plan_steps: int = 8
    max_replan_count: int = 3

    @property
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        return {
            "shopify": {"transport": self.mcp_shopify_transport, "url": self.mcp_shopify_url},
            "ads": {"transport": self.mcp_ads_transport, "url": self.mcp_ads_url},
        }


config = Settings()
