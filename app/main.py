"""FastAPI 应用入口 - Shopify AI Assistant"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.config import config
from loguru import logger
from app.api import chat, health, file, ops, snapshot, config as config_api
from app.core.milvus_client import milvus_manager

static_dir = "static"
assets_dir = os.path.join(static_dir, "assets")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"Shopify AI Assistant v{config.app_version} 启动中...")
    logger.info(f"环境: {'开发' if config.debug else '生产'}")
    logger.info(f"监听地址: http://{config.host}:{config.port}")
    logger.info(f"API 文档: http://{config.host}:{config.port}/docs")
    logger.info("正在连接 Milvus...")
    milvus_manager.connect()
    logger.info("Milvus 连接成功")
    logger.info("=" * 60)

    yield

    logger.info("正在关闭 Milvus 连接...")
    milvus_manager.close()
    logger.info("Shopify AI Assistant 已关闭")


app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="基于 LangChain + LangGraph 的 Shopify 独立站运营 AI 助手",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API 路由 ────────────────────────────────────────────────
app.include_router(health.router, tags=["健康检查"])
app.include_router(chat.router, prefix="/api", tags=["知识库问答"])
app.include_router(file.router, prefix="/api", tags=["文件管理"])
app.include_router(ops.router, prefix="/api", tags=["运营 Agent"])
app.include_router(snapshot.router, prefix="/api", tags=["数据快照"])
app.include_router(config_api.router, prefix="/api", tags=["配置信息"])

# ── 前端静态资源挂载（必须在 catch-all 路由之前）──────────────
# /assets/* → static/assets/
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


# ── 前端页面路由 ────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": f"Welcome to {config.app_name}", "docs": "/docs"}


# SPA fallback：/chat /knowledge /settings 都返回 index.html 交给 React Router
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    # 这些路径不走 fallback
    skip = ("api/", "docs", "openapi.json", "redoc", "assets/")
    if any(full_path.startswith(p) for p in skip):
        raise HTTPException(status_code=404)
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.host, port=config.port, reload=config.debug)
