"""不暴露内部依赖详情的精简健康检查。"""

from fastapi import APIRouter
from app.config import config

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": config.app_name, "version": config.app_version}
