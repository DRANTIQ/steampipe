"""FastAPI dependencies: DB session, JWT auth (T-022)."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.enums import UserRole
from src.services.auth import TokenPayload, decode_access_token
from src.services.database import get_db_session_factory

_bearer = HTTPBearer(auto_error=False)


def get_db_session():
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


DbSession = Annotated[Session, Depends(get_db_session)]


def _token_from_header(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenPayload | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        return decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_optional_auth(
    token: TokenPayload | None = Depends(_token_from_header),
) -> TokenPayload | None:
    return token


def enforce_auth_when_required(
    token: TokenPayload | None = Depends(_token_from_header),
) -> TokenPayload | None:
    """When API_AUTH_REQUIRED=true, reject unauthenticated requests."""
    settings = get_settings()
    if settings.API_AUTH_REQUIRED and not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return token


def require_auth(
    token: TokenPayload | None = Depends(_token_from_header),
) -> TokenPayload:
    if token:
        return token
    raise HTTPException(status_code=401, detail="Authentication required")


AuthUser = Annotated[TokenPayload, Depends(require_auth)]


def require_super_admin(auth: AuthUser) -> TokenPayload:
    if auth.role != UserRole.super_admin.value:
        raise HTTPException(status_code=403, detail="super_admin required")
    return auth


SuperAdmin = Annotated[TokenPayload, Depends(require_super_admin)]


def require_role(*roles: str):
    def _check(auth: AuthUser) -> TokenPayload:
        if auth.role not in roles and auth.role != UserRole.super_admin.value:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return auth

    return _check


def is_super_admin(auth: TokenPayload) -> bool:
    return auth.role == UserRole.super_admin.value


def assert_tenant_access(auth: TokenPayload, tenant_id: str) -> None:
    """Non-super_admin users may only access their own tenant."""
    if is_super_admin(auth):
        return
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")


def resolve_list_tenant_filter(auth: TokenPayload, tenant_id: str | None) -> str | None:
    """List endpoints: scope non-super_admin to their tenant."""
    if is_super_admin(auth):
        return tenant_id
    return auth.tenant_id
