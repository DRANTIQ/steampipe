"""JWT issue/verify and password checks (T-022)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from src.config import get_settings

ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    tenant_id: str
    role: str
    email: str


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(
    *,
    user_id: str,
    tenant_id: str,
    role: str,
    email: str,
    expires_minutes: int | None = None,
) -> str:
    settings = get_settings()
    ttl = expires_minutes if expires_minutes is not None else settings.JWT_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("invalid_token") from exc
    user_id = data.get("sub")
    tenant_id = data.get("tenant_id")
    role = data.get("role")
    email = data.get("email")
    if not user_id or not tenant_id or not role:
        raise ValueError("invalid_token")
    return TokenPayload(
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        role=str(role),
        email=str(email or ""),
    )
