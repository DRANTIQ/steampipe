"""FastAPI dependencies: DB session, tenant context."""
from __future__ import annotations

import uuid
from collections.abc import Generator

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, set_tenant_id


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_tenant_id(x_tenant_id: str | None = Header(None, alias="X-Tenant-Id")) -> str:
    """Require X-Tenant-Id header (UUID). For dev, fallback to DEFAULT_TENANT_ID."""
    if x_tenant_id:
        try:
            uuid.UUID(x_tenant_id)
            return x_tenant_id
        except ValueError:
            raise HTTPException(422, "X-Tenant-Id must be a valid UUID")
    settings = get_settings()
    if settings.DEFAULT_TENANT_ID:
        return settings.DEFAULT_TENANT_ID
    raise HTTPException(400, "X-Tenant-Id header required")


def get_db_with_tenant(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Session:
    """DB session with RLS tenant context set."""
    set_tenant_id(db, tenant_id)
    return db
