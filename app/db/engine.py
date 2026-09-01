"""SQLAlchemy engine and transaction helpers."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import config


class Base(DeclarativeBase):
    pass


def _ensure_database_directory() -> None:
    if config.database_url.startswith("sqlite:///"):
        raw_path = config.database_url.removeprefix("sqlite:///")
        Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_ensure_database_directory()
engine = create_engine(
    config.database_url,
    connect_args={"check_same_thread": False} if config.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)


if config.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_safety(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
