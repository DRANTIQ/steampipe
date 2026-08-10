"""Database session management. Schema is applied only via migrations."""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.config.settings import postgres_connect_args


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def build_engine(**engine_kwargs) -> Engine:
    """Create SQLAlchemy engine with optional IPv4 hostaddr for cloud Postgres from Docker."""
    settings = get_settings()
    connect_args = postgres_connect_args(settings.DATABASE_URL, settings.DATABASE_PREFER_IPV4)
    kwargs = {
        "pool_pre_ping": True,
        "connect_args": connect_args,
        **engine_kwargs,
    }
    if "poolclass" not in kwargs and "pool_size" not in kwargs:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
    return create_engine(settings.DATABASE_URL, **kwargs)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_db_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _SessionLocal


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Provide a transactional scope. Caller must not hold session across requests."""
    factory = get_db_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Ensure engine is created. Does NOT create tables; use alembic for schema."""
    get_engine()
    get_db_session_factory()
