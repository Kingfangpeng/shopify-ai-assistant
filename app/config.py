"""配置管理模块 - Shopify AI Assistant"""

from pathlib import Path
from typing import Dict, Any
from pydantic import field_validator
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
    host: str = "127.0.0.1"
    port: int = 9901
    allowed_hosts: str = "127.0.0.1,localhost,testserver"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

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
    shopify_api_version: str = "2026-07"
    shopify_access_token: str = ""
    shopify_webhook_secret: str = ""
    shopify_demo_mode: bool = False
    shopify_low_stock_threshold: int = 10

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

    # ── 本地数据库与认证 ───────────────────────────────────────────
    database_url: str = "sqlite:///./volumes/app/shopify_ai.db"
    auth_secret_key: str = ""
    auth_cookie_name: str = "shopify_ai_session"
    auth_session_hours: int = 8
    auth_idle_minutes: int = 60
    auth_cookie_secure: bool = False
    login_max_attempts: int = 5
    login_window_minutes: int = 15

    # ── 本地数据目录 ───────────────────────────────────────────────
    upload_dir: str = "./uploads"
    trash_dir: str = "./uploads/.trash"
    trash_retention_days: int = 7
    max_upload_bytes: int = 10 * 1024 * 1024
    ads_enabled: bool = False

    @field_validator("host")
    @classmethod
    def _local_host_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost"}:
            raise ValueError("本应用仅允许监听 127.0.0.1 或 localhost")
        return value

    @field_validator("shopify_api_version")
    @classmethod
    def _fixed_shopify_version(cls, value: str) -> str:
        if value != "2026-07":
            raise ValueError("Shopify Admin API 必须固定为 2026-07")
        return value

    @property
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        servers: Dict[str, Dict[str, Any]] = {
            "shopify": {"transport": self.mcp_shopify_transport, "url": self.mcp_shopify_url},
        }
        if self.ads_enabled:
            servers["ads"] = {"transport": self.mcp_ads_transport, "url": self.mcp_ads_url}
        return servers

    @property
    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()

    @property
    def trash_path(self) -> Path:
        return Path(self.trash_dir).resolve()


config = Settings()
