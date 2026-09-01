from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import config
from app.core.errors import AppError
from app.db.engine import Base
from app.services.knowledge.service import knowledge_service
from app.services.vector_store_manager import vector_store_manager


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def safe_vectors(monkeypatch):
    stored = []
    monkeypatch.setattr(vector_store_manager, "add_documents", lambda docs: stored.extend(docs) or [str(i) for i in range(len(docs))])
    monkeypatch.setattr(vector_store_manager, "delete_document_version", lambda *_args, **_kwargs: 1)
    return stored


@pytest.mark.asyncio
async def test_upload_sanitizes_path_and_uses_server_storage_id(tmp_path, monkeypatch, db, safe_vectors):
    monkeypatch.setattr(config, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "trash_dir", str(tmp_path / "uploads" / ".trash"))
    upload = UploadFile(filename="../../产品.md", file=BytesIO("# 产品\n安全内容".encode()))
    document = await knowledge_service.upload(db, "user-1", upload)
    assert document.original_name == "产品.md"
    assert ".." not in document.storage_name
    assert (config.upload_path / document.storage_name).is_file()
    assert all(item.metadata["document_id"] == document.id for item in safe_vectors)
    assert all("_source" not in item.metadata for item in safe_vectors)


@pytest.mark.asyncio
async def test_invalid_utf8_is_rejected(tmp_path, monkeypatch, db, safe_vectors):
    monkeypatch.setattr(config, "upload_dir", str(tmp_path / "uploads"))
    upload = UploadFile(filename="bad.txt", file=BytesIO(b"\xff\xfe"))
    with pytest.raises(AppError) as error:
        await knowledge_service.upload(db, "user-1", upload)
    assert error.value.code == "invalid_encoding"


@pytest.mark.asyncio
async def test_failed_update_preserves_old_source(tmp_path, monkeypatch, db, safe_vectors):
    monkeypatch.setattr(config, "upload_dir", str(tmp_path / "uploads"))
    first = UploadFile(filename="guide.md", file=BytesIO(b"# old\nold content"))
    document = await knowledge_service.upload(db, "user-1", first)
    db.commit()
    source = config.upload_path / document.storage_name
    old_bytes = source.read_bytes()
    monkeypatch.setattr(vector_store_manager, "add_documents", lambda _docs: (_ for _ in ()).throw(RuntimeError("embedding down")))
    second = UploadFile(filename="guide.md", file=BytesIO(b"# new\nnew content"))
    with pytest.raises(RuntimeError, match="embedding down"):
        await knowledge_service.upload(db, "user-1", second)
    assert source.read_bytes() == old_bytes


@pytest.mark.asyncio
async def test_failed_old_vector_removal_restores_old_source(tmp_path, monkeypatch, db, safe_vectors):
    monkeypatch.setattr(config, "upload_dir", str(tmp_path / "uploads"))
    first = UploadFile(filename="guide.md", file=BytesIO(b"# old\nold content"))
    document = await knowledge_service.upload(db, "user-1", first)
    db.commit()
    source = config.upload_path / document.storage_name
    old_bytes = source.read_bytes()

    def fail_old_version(_document_id, version):
        if version == 1:
            raise RuntimeError("old vector removal failed")
        return 1

    monkeypatch.setattr(vector_store_manager, "delete_document_version", fail_old_version)
    second = UploadFile(filename="guide.md", file=BytesIO(b"# new\nnew content"))
    with pytest.raises(RuntimeError, match="old vector removal failed"):
        await knowledge_service.upload(db, "user-1", second)
    assert source.read_bytes() == old_bytes
