"""Tenant user management (super_admin)."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import AuthUser, SuperAdmin, assert_tenant_access
from src.api.deps import DbSession
from src.api.schemas import UserCreate, UserResponse, UserUpdate
from src.models import Tenant, User
from src.models.enums import UserRole
from src.services.auth import hash_password

router = APIRouter()

_ALLOWED_ROLES = {
    UserRole.tenant_admin.value,
    UserRole.tenant_user.value,
    UserRole.viewer.value,
}


def _validate_role(role: str) -> None:
    if role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role; allowed: {sorted(_ALLOWED_ROLES)}")


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/{tenant_id}/users", response_model=list[UserResponse])
def list_tenant_users(
    session: DbSession,
    tenant_id: str,
    auth: AuthUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[UserResponse]:
    assert_tenant_access(auth, tenant_id)
    tenant = session.query(Tenant).filter(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    users = (
        session.query(User)
        .filter(User.tenant_id == tenant_id)
        .order_by(User.email)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_user_response(u) for u in users]


@router.post("/{tenant_id}/users", response_model=UserResponse)
def create_tenant_user(
    session: DbSession,
    tenant_id: str,
    body: UserCreate,
    auth: SuperAdmin,
) -> UserResponse:
    tenant = session.query(Tenant).filter(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if body.role == UserRole.super_admin.value:
        raise HTTPException(status_code=400, detail="super_admin users cannot be created via tenant API")
    _validate_role(body.role)
    email = body.email.strip().lower()
    existing = session.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        id=str(uuid4()),
        tenant_id=tenant_id,
        email=email,
        username=body.username or email.split("@")[0],
        hashed_password=hash_password(body.password),
        role=body.role,
        active=True,
    )
    session.add(user)
    session.flush()
    return _user_response(user)


@router.patch("/{tenant_id}/users/{user_id}", response_model=UserResponse)
def update_tenant_user(
    session: DbSession,
    tenant_id: str,
    user_id: str,
    body: UserUpdate,
    auth: SuperAdmin,
) -> UserResponse:
    user = session.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.email is not None:
        email = body.email.strip().lower()
        clash = session.query(User).filter(User.email == email, User.id != user_id).first()
        if clash:
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = email
    if body.username is not None:
        user.username = body.username
    if body.role is not None:
        if body.role == UserRole.super_admin.value:
            raise HTTPException(status_code=400, detail="Cannot assign super_admin via API")
        _validate_role(body.role)
        user.role = body.role
    if body.active is not None:
        user.active = body.active
    if body.password:
        user.hashed_password = hash_password(body.password)
    session.flush()
    return _user_response(user)


@router.delete("/{tenant_id}/users/{user_id}", status_code=204)
def deactivate_tenant_user(
    session: DbSession,
    tenant_id: str,
    user_id: str,
    auth: SuperAdmin,
) -> None:
    user = session.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.active = False
    session.flush()
