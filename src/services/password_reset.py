"""Create and consume password reset / invite tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import PasswordResetToken, User
from src.services.email import send_password_reset_email


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _reset_url(token: str) -> str:
    settings = get_settings()
    base = settings.APP_PUBLIC_URL.rstrip("/")
    return f"{base}/reset-password?token={token}"


def create_password_token(
    session: Session,
    user: User,
    *,
    purpose: str = "reset",
) -> str:
    """Issue a one-time token; returns the plain token for the email link."""
    settings = get_settings()
    plain = secrets.token_urlsafe(32)
    row = PasswordResetToken(
        id=str(uuid4()),
        user_id=user.id,
        token_hash=_hash_token(plain),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_RESET_EXPIRE_HOURS),
    )
    session.add(row)
    session.flush()
    return plain


def send_reset_email(session: Session, user: User, *, purpose: str = "reset") -> None:
    plain = create_password_token(session, user, purpose=purpose)
    send_password_reset_email(to=user.email, reset_url=_reset_url(plain), purpose=purpose)


def consume_password_token(session: Session, plain_token: str) -> User | None:
    token_hash = _hash_token(plain_token)
    row = (
        session.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        )
        .first()
    )
    if not row:
        return None
    now = datetime.now(timezone.utc)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        return None
    user = session.get(User, row.user_id)
    if not user or not user.active:
        return None
    row.used_at = now
    session.flush()
    return user
