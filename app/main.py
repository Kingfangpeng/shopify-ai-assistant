"""FastAPI 应用入口。"""

from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import auth, chat, config as config_api, file, health, ops, snapshot
from app.auth.dependencies import get_current_user
from app.auth.middleware import RequestSecurityMiddleware
from app.config import config
from app.core.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.core.milvus_client import milvus_manager
from app.db.engine import db_session, init_db
from app.db.models import ChatMessage
from sqlalchemy import update
from app.services.knowledge import knowledge_service

static_dir = "static"
assets_dir = os.path.join(static_dir, "assets")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with db_session() as db:
        db.execute(update(ChatMessage).where(ChatMessage.status == "running").values(
            status="interrupted", content="服务已重启，之前的分析已中断；可查看已保存过程后重试。",
        ))
        purged = knowledge_service.cleanup_expired(db)
    stop_cleanup = asyncio.Event()

    async def cleanup_loop() -> None:
        while not stop_cleanup.is_set():
            try:
                await asyncio.wait_for(stop_cleanup.wait(), timeout=6 * 60 * 60)
            except TimeoutError:
                with db_session() as cleanup_db:
                    knowledge_service.cleanup_expired(cleanup_db)

    cleanup_task = asyncio.create_task(cleanup_loop())
    logger.info(f"{config.app_name} v{config.app_version} 已启动（{config.host}:{config.port}），清理回收站 {purged} 项")
    try:
        yield
    finally:
        stop_cleanup.set()
        await cleanup_task
        milvus_manager.close()


app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="本地优先的 Shopify GraphQL 运营助手",
    lifespan=lifespan,
    docs_url="/docs" if config.debug else None,
    redoc_url="/redoc" if config.debug else None,
    openapi_url="/openapi.json" if config.debug else None,
)
app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(HTTPException, http_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unexpected_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_host_list)
app.add_middleware(RequestSecurityMiddleware)

auth_required = [Depends(get_current_user)]
app.include_router(health.router, tags=["健康检查"])
app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(chat.router, prefix="/api", tags=["知识库问答"], dependencies=auth_required)
app.include_router(file.router, prefix="/api", tags=["知识库"], dependencies=auth_required)
app.include_router(ops.router, prefix="/api", tags=["运营 Agent"], dependencies=auth_required)
app.include_router(snapshot.router, prefix="/api", tags=["Shopify 数据"], dependencies=auth_required)
app.include_router(config_api.router, prefix="/api", tags=["配置信息"], dependencies=auth_required)

if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/", include_in_schema=False)
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": config.app_name}


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if any(full_path.startswith(prefix) for prefix in ("api/", "docs", "openapi.json", "redoc", "assets/")):
        raise HTTPException(status_code=404)
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.host, port=config.port, reload=config.debug)
