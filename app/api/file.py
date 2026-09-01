"""文件上传接口模块"""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.services.vector_index_service import vector_index_service
from loguru import logger

router = APIRouter()

UPLOAD_DIR = Path("./uploads")
ALLOWED_EXTENSIONS = ["txt", "md"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件并自动创建向量索引"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        safe_filename = _sanitize_filename(file.filename)
        file_extension = _get_file_extension(safe_filename)
        if file_extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式，仅支持: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_path = UPLOAD_DIR / safe_filename

        if file_path.exists():
            logger.info(f"文件已存在，将覆盖: {file_path}")
            file_path.unlink()

        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE} 字节）")

        file_path.write_bytes(content)
        logger.info(f"文件上传成功: {file_path}")

        try:
            logger.info(f"开始为上传文件创建向量索引: {file_path}")
            vector_index_service.index_single_file(str(file_path))
            logger.info(f"向量索引创建成功: {file_path}")
        except Exception as e:
            logger.error(f"向量索引创建失败: {file_path}, 错误: {e}")

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "filename": safe_filename,
                    "file_path": str(file_path),
                    "size": len(content),
                },
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")


@router.post("/index_directory")
async def index_directory(directory_path: str = None):
    """索引指定目录下的所有文件"""
    try:
        logger.info(f"开始索引目录: {directory_path or 'uploads'}")
        result = vector_index_service.index_directory(directory_path)
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success" if result.success else "partial_success",
                "data": result.to_dict(),
            },
        )
    except Exception as e:
        logger.error(f"索引目录失败: {e}")
        raise HTTPException(status_code=500, detail=f"索引目录失败: {e}")


@router.get("/knowledge/chunks")
@router.get("/chunks")
async def list_knowledge_chunks(
    file_path: str = None,
    filename: str = None,
    limit: int = 50,
    offset: int = 0,
):
    """查询知识库中的文档分片"""
    try:
        from app.services.vector_store_manager import vector_store_manager
        chunks = vector_store_manager.list_chunks(
            file_path=file_path,
            filename=filename,
            limit=limit,
            offset=offset,
        )
        return JSONResponse(status_code=200, content={"code": 200, "message": "success", "data": chunks})
    except Exception as e:
        logger.error(f"查询分片失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询分片失败: {e}")


@router.get("/knowledge/stats")
@router.get("/knowledge_stats")
async def get_knowledge_stats():
    """获取知识库统计信息"""
    try:
        from app.services.vector_store_manager import vector_store_manager
        stats = vector_store_manager.get_stats()
        return JSONResponse(status_code=200, content={"code": 200, "message": "success", "data": stats})
    except Exception as e:
        logger.error(f"获取知识库统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取知识库统计失败: {e}")


@router.delete("/knowledge/file")
async def delete_knowledge_file(file_path: str):
    """删除知识库中指定文件的所有分片"""
    try:
        from app.services.vector_store_manager import vector_store_manager
        deleted = vector_store_manager.delete_by_file(file_path)
        return JSONResponse(status_code=200, content={"code": 200, "message": "success", "data": {"deleted": deleted}})
    except Exception as e:
        logger.error(f"删除知识库文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除知识库文件失败: {e}")


def _get_file_extension(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        return parts[1].lower()
    return ""


def _sanitize_filename(filename: str) -> str:
    sanitized = filename.replace(" ", "_")
    for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        sanitized = sanitized.replace(char, "_")
    return sanitized
