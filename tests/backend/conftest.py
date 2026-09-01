import os

os.environ["DATABASE_URL"] = "sqlite:///./volumes/test/shopify_ai_test.db"
os.environ["AUTH_SECRET_KEY"] = "test-auth-secret-that-is-long-and-local-only"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_MODEL"] = "gpt-4o-mini"
os.environ["RAG_MODEL"] = "gpt-4o-mini"
os.environ["SHOPIFY_STORE_DOMAIN"] = ""
os.environ["SHOPIFY_ACCESS_TOKEN"] = ""
os.environ["SHOPIFY_DEMO_MODE"] = "false"

import pytest

from app.auth.service import login_limiter
from app.db.engine import Base, engine


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_limiter._attempts.clear()
    yield
    Base.metadata.drop_all(engine)
