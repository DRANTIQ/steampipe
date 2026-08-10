"""POST /api/v1/auth/login — JWT for UI and API clients (T-022)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import DbSession, get_optional_auth
from src.models.user import User
from src.services.auth import TokenPayload, create_access_token, hash_password, verify_password
from src.services.password_reset import consume_password_token, send_reset_email

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    role: str
    email: str


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str
    role: str
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


class MessageResponse(BaseModel):
    message: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: DbSession):
    user = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.last_login = datetime.now(timezone.utc)
    db.flush()
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )


@router.get("/me", response_model=MeResponse)
def me(auth: TokenPayload = Depends(get_optional_auth)):
    if not auth:
        raise HTTPException(status_code=401, detail="Authentication required")
    return MeResponse(
        user_id=auth.user_id,
        tenant_id=auth.tenant_id,
        role=auth.role,
        email=auth.email,
    )


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(body: ForgotPasswordRequest, db: DbSession) -> MessageResponse:
    """Request a password reset link. Always returns success to avoid email enumeration."""
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email, User.active == True).first()
    if user:
        send_reset_email(db, user, purpose="reset")
    return MessageResponse(
        message="If an account exists for that email, a reset link has been sent.",
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, db: DbSession) -> MessageResponse:
    user = consume_password_token(db, body.token.strip())
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user.hashed_password = hash_password(body.password)
    db.flush()
    return MessageResponse(message="Password updated. You can sign in now.")
