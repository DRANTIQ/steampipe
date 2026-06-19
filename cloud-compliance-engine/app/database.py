"""DB engine and session for compliance schema. Uses same DATABASE_URL as parent."""
from __future__ import annotations

from collections.abc import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models.compliance import ComplianceBase


def get_engine():
    settings = get_settings()
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        echo=False,
    )


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield DB session for FastAPI Depends; commit on success, rollback on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_tenant_id(db: Session, tenant_id: str) -> None:
    """Set app.tenant_id for RLS. Call at start of request."""
    db.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant_id})
