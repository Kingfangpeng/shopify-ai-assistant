"""启动可重复的 E2E 服务。仅使用隔离数据库和测试替身。"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
run_id = str(os.getpid())
os.environ["DATABASE_URL"] = f"sqlite:///./volumes/e2e/playwright-{run_id}.db"
os.environ["AUTH_SECRET_KEY"] = "playwright-only-auth-secret"
os.environ["LLM_API_KEY"] = "playwright-test-key"
os.environ["SHOPIFY_STORE_DOMAIN"] = ""
os.environ["SHOPIFY_ACCESS_TOKEN"] = ""
os.environ["SHOPIFY_DEMO_MODE"] = "true"
os.environ["UPLOAD_DIR"] = f"./volumes/e2e/playwright-uploads-{run_id}"
os.environ["TRASH_DIR"] = f"./volumes/e2e/playwright-uploads-{run_id}/.trash"

import uvicorn
from sqlalchemy import select

from app.auth.service import auth_service
from app.db.engine import db_session, init_db
from app.db.models import User


def ensure_admin() -> None:
    init_db()
    with db_session() as db:
        if not db.scalar(select(User).where(User.username == "king")):
            auth_service.create_admin(db, "king", "Local-QA-Password-2026")


if __name__ == "__main__":
    ensure_admin()
    uvicorn.run("tests.e2e.server:app", host="127.0.0.1", port=9901, log_level="warning")
