"""上传、索引、回收站与恢复的事务式生命周期。"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.service import auth_service
from app.config import config
from app.core.errors import AppError
from app.db.models import KnowledgeDocument, utcnow
from app.services.document_splitter_service import document_splitter_service
from app.services.vector_store_manager import vector_store_manager

ALLOWED_EXTENSIONS = {".txt", ".md"}


class KnowledgeService:
    async def upload(self, db: Session, user_id: str, upload: UploadFile) -> KnowledgeDocument:
        original_name = self._safe_filename(upload.filename or "")
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise AppError("unsupported_file_type", "仅支持 UTF-8 编码的 .txt 和 .md 文件", 422)

        config.upload_path.mkdir(parents=True, exist_ok=True)
        temp_dir = config.upload_path / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / str(uuid4())
        digest = hashlib.sha256()
        size = 0
        try:
            with temp_path.open("wb") as handle:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > config.max_upload_bytes:
                        raise AppError("file_too_large", f"文件不能超过 {config.max_upload_bytes} 字节", 413)
                    digest.update(chunk)
                    handle.write(chunk)
            raw = temp_path.read_bytes()
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise AppError("invalid_encoding", "文件必须使用 UTF-8 编码", 422) from exc
            if not content.strip():
                raise AppError("empty_file", "文件内容不能为空", 422)
            sha256 = digest.hexdigest()
            duplicate = db.scalar(select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.sha256 == sha256,
                KnowledgeDocument.status == "active",
            ))
            if duplicate:
                raise AppError("duplicate_document", "相同内容已存在于知识库", 409)

            document = db.scalar(select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.original_name == original_name,
                KnowledgeDocument.status == "active",
            ))
            old_version = document.version if document else None
            if document is None:
                document = KnowledgeDocument(
                    user_id=user_id,
                    original_name=original_name,
                    storage_name=f"{uuid4()}{suffix}",
                    sha256=sha256,
                    size_bytes=size,
                    status="indexing",
                    version=1,
                )
                db.add(document)
                db.flush()
            new_version = (old_version or 0) + 1 if old_version else 1
            documents = self._split(content, original_name, document.id, new_version)
            vector_store_manager.add_documents(documents)
            destination = config.upload_path / document.storage_name
            backup: Path | None = None
            try:
                backup = self._replace_source(temp_path, destination)
                if old_version is not None:
                    vector_store_manager.delete_document_version(document.id, old_version)
            except Exception:
                self._restore_source(destination, backup)
                try:
                    vector_store_manager.delete_document_version(document.id, new_version)
                except Exception:
                    pass
                raise
            if backup:
                backup.unlink(missing_ok=True)

            document.sha256 = sha256
            document.size_bytes = size
            document.chunk_count = len(documents)
            document.version = new_version
            document.status = "active"
            document.updated_at = utcnow()
            auth_service.audit(db, user_id, "knowledge_uploaded", "knowledge_document", document.id,
                               {"name": original_name, "size": size, "version": new_version})
            return document
        finally:
            await upload.close()
            temp_path.unlink(missing_ok=True)

    def list_documents(self, db: Session, user_id: str, status: str, limit: int, offset: int) -> dict:
        allowed = {"active", "trashed"}
        if status not in allowed:
            raise AppError("invalid_status", "知识库状态无效", 422)
        rows = list(db.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user_id,
                KnowledgeDocument.status == status,
            ).order_by(KnowledgeDocument.updated_at.desc()).offset(max(0, offset)).limit(max(1, min(limit, 100)))
        ))
        return {"items": [self.serialize(item) for item in rows], "limit": limit, "offset": offset}

    def get(self, db: Session, user_id: str, document_id: str) -> KnowledgeDocument:
        document = db.scalar(select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.user_id == user_id,
        ))
        if not document:
            raise AppError("document_not_found", "知识库文档不存在", 404)
        return document

    def chunks(self, db: Session, user_id: str, document_id: str, limit: int, offset: int) -> dict:
        document = self.get(db, user_id, document_id)
        if document.status != "active":
            raise AppError("document_trashed", "回收站文档没有可查询的向量分片", 409)
        return vector_store_manager.list_chunks(document.id, limit, offset)

    def trash(self, db: Session, user_id: str, document_id: str) -> None:
        document = self.get(db, user_id, document_id)
        if document.status != "active":
            raise AppError("document_already_trashed", "文档已在回收站", 409)
        source = config.upload_path / document.storage_name
        target = config.trash_path / document.storage_name
        config.trash_path.mkdir(parents=True, exist_ok=True)
        vector_store_manager.delete_document_version(document.id, document.version)
        try:
            os.replace(source, target)
        except Exception:
            self._index_file(source, document)
            raise
        now = utcnow()
        document.status = "trashed"
        document.trashed_at = now
        document.delete_after = now + timedelta(days=config.trash_retention_days)
        document.updated_at = now
        auth_service.audit(db, user_id, "knowledge_deleted", "knowledge_document", document.id)

    def restore(self, db: Session, user_id: str, document_id: str) -> KnowledgeDocument:
        document = self.get(db, user_id, document_id)
        if document.status != "trashed":
            raise AppError("document_not_trashed", "文档不在回收站", 409)
        source = config.trash_path / document.storage_name
        target = config.upload_path / document.storage_name
        if not source.is_file():
            raise AppError("trashed_file_missing", "回收站源文件丢失，无法恢复", 409)
        new_version = document.version + 1
        content = source.read_text(encoding="utf-8")
        documents = self._split(content, document.original_name, document.id, new_version)
        vector_store_manager.add_documents(documents)
        try:
            os.replace(source, target)
        except Exception:
            vector_store_manager.delete_document_version(document.id, new_version)
            raise
        document.status = "active"
        document.version = new_version
        document.chunk_count = len(documents)
        document.trashed_at = None
        document.delete_after = None
        document.updated_at = utcnow()
        auth_service.audit(db, user_id, "knowledge_restored", "knowledge_document", document.id)
        return document

    def rebuild(self, db: Session, user_id: str) -> dict:
        documents = list(db.scalars(select(KnowledgeDocument).where(
            KnowledgeDocument.user_id == user_id,
            KnowledgeDocument.status == "active",
        )))
        rebuilt = 0
        failures: list[dict[str, str]] = []
        for document in documents:
            try:
                self._index_file(config.upload_path / document.storage_name, document)
                rebuilt += 1
            except Exception:
                failures.append({"document_id": document.id, "message": "重建失败，旧版本已保留"})
        auth_service.audit(db, user_id, "knowledge_rebuilt", "knowledge_document", None,
                           {"rebuilt": rebuilt, "failed": len(failures)})
        return {"rebuilt": rebuilt, "failed": failures}

    def cleanup_expired(self, db: Session) -> int:
        expired = list(db.scalars(select(KnowledgeDocument).where(
            KnowledgeDocument.status == "trashed",
            KnowledgeDocument.delete_after <= utcnow(),
        )))
        for document in expired:
            (config.trash_path / document.storage_name).unlink(missing_ok=True)
            db.delete(document)
        return len(expired)

    def _index_file(self, path: Path, document: KnowledgeDocument) -> None:
        content = path.read_text(encoding="utf-8")
        new_version = document.version + 1
        chunks = self._split(content, document.original_name, document.id, new_version)
        vector_store_manager.add_documents(chunks)
        try:
            vector_store_manager.delete_document_version(document.id, document.version)
        except Exception:
            vector_store_manager.delete_document_version(document.id, new_version)
            raise
        document.version = new_version
        document.chunk_count = len(chunks)
        document.updated_at = utcnow()

    @staticmethod
    def _split(content: str, name: str, document_id: str, version: int):
        documents = document_splitter_service.split_document(content, name)
        if not documents:
            raise AppError("document_has_no_chunks", "文件没有可索引内容", 422)
        for chunk in documents:
            chunk.page_content = "".join(char for char in chunk.page_content if char in "\n\t" or ord(char) >= 32)
            chunk.metadata.pop("_source", None)
            chunk.metadata["document_id"] = document_id
            chunk.metadata["version"] = version
            chunk.metadata["file_name"] = name
        return documents

    @staticmethod
    def _replace_source(temp_path: Path, destination: Path) -> Path | None:
        backup = destination.with_name(f"{destination.name}.bak-{uuid4()}") if destination.exists() else None
        if destination.exists():
            assert backup is not None
            os.replace(destination, backup)
        try:
            os.replace(temp_path, destination)
        except Exception:
            if backup and backup.exists():
                os.replace(backup, destination)
            raise
        return backup

    @staticmethod
    def _restore_source(destination: Path, backup: Path | None) -> None:
        if backup and backup.exists():
            destination.unlink(missing_ok=True)
            os.replace(backup, destination)
        elif backup is None:
            destination.unlink(missing_ok=True)

    @staticmethod
    def _safe_filename(value: str) -> str:
        name = Path(value.replace("\\", "/")).name.strip()
        name = re.sub(r"[^\w.\- ()\u4e00-\u9fff]", "_", name, flags=re.UNICODE)
        if not name or name in {".", ".."} or len(name) > 255:
            raise AppError("invalid_filename", "文件名无效", 422)
        return name

    @staticmethod
    def serialize(document: KnowledgeDocument) -> dict:
        return {
            "id": document.id,
            "name": document.original_name,
            "size_bytes": document.size_bytes,
            "sha256": document.sha256,
            "status": document.status,
            "chunk_count": document.chunk_count,
            "version": document.version,
            "updated_at": document.updated_at.isoformat() + "Z",
            "delete_after": document.delete_after.isoformat() + "Z" if document.delete_after else None,
        }


knowledge_service = KnowledgeService()
