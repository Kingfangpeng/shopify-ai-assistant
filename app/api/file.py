"""安全知识库 HTTP 接口；客户端只能使用服务端文档 ID。"""

from fastapi import APIRouter, Depends, File, UploadFile

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.errors import AppError
from app.db.engine import db_session
from app.services.knowledge import knowledge_service

router = APIRouter()


@router.get("/knowledge/documents")
async def list_documents(
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
    context: AuthContext = Depends(get_auth_context),
):
    with db_session() as db:
        return knowledge_service.list_documents(db, context.user.id, status, limit, offset)


@router.post("/knowledge/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        document = await knowledge_service.upload(db, context.user.id, file)
        return knowledge_service.serialize(document)


@router.get("/knowledge/documents/{document_id}/chunks")
async def document_chunks(
    document_id: str,
    limit: int = 50,
    offset: int = 0,
    context: AuthContext = Depends(get_auth_context),
):
    with db_session() as db:
        return knowledge_service.chunks(db, context.user.id, document_id, limit, offset)


@router.delete("/knowledge/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        knowledge_service.trash(db, context.user.id, document_id)


@router.post("/knowledge/documents/{document_id}/restore")
async def restore_document(document_id: str, context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        document = knowledge_service.restore(db, context.user.id, document_id)
        return knowledge_service.serialize(document)


@router.post("/knowledge/rebuild")
async def rebuild_knowledge(context: AuthContext = Depends(get_auth_context)):
    with db_session() as db:
        return knowledge_service.rebuild(db, context.user.id)


@router.post("/upload", include_in_schema=False)
@router.post("/index_directory", include_in_schema=False)
async def legacy_knowledge_endpoint():
    raise AppError(
        "knowledge_api_moved",
        "旧知识库接口已停用，请迁移到 /api/knowledge/documents 和 /api/knowledge/rebuild",
        410,
    )
