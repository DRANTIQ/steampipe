"""FastAPI dependencies: DB session, JWT auth (T-022)."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.config import get_settings
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
    settings = get_settings()
    if token:
        return token
    if not settings.API_AUTH_REQUIRED:
        raise HTTPException(status_code=401, detail="Authentication required")
    raise HTTPException(status_code=401, detail="Authentication required")


def require_role(*roles: str):
    def _check(auth: TokenPayload = Depends(require_auth)) -> TokenPayload:
        if auth.role not in roles and auth.role != "super_admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return auth

    return _check
