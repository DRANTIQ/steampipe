"""POST /api/v1/auth/login — JWT for UI and API clients (T-022)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import DbSession, get_optional_auth
from src.models.user import User
from src.services.auth import TokenPayload, create_access_token, verify_password

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
