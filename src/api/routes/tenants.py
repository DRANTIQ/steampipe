from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import AuthUser, SuperAdmin, assert_tenant_access, is_super_admin
from src.api.deps import DbSession
from src.api.schemas import TenantCreate, TenantResponse
from src.models import Tenant

router = APIRouter()


@router.post("", response_model=TenantResponse)
def create_tenant(session: DbSession, body: TenantCreate, auth: SuperAdmin) -> Tenant:
    existing = session.query(Tenant).filter(Tenant.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Tenant with this name already exists")
    tenant = Tenant(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        plan_type=body.plan_type,
        max_accounts=body.max_accounts,
        max_queries=body.max_queries,
        max_executions_per_day=body.max_executions_per_day,
    )
    session.add(tenant)
    session.flush()
    return tenant


@router.get("", response_model=list[TenantResponse])
def list_tenants(
    session: DbSession,
    auth: AuthUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    active: bool | None = None,
) -> list[Tenant]:
    q = session.query(Tenant).filter(Tenant.deleted_at.is_(None))
    if not is_super_admin(auth):
        q = q.filter(Tenant.id == auth.tenant_id)
    if active is not None:
        q = q.filter(Tenant.active == active)
    return q.offset(skip).limit(limit).all()


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(session: DbSession, tenant_id: str, auth: AuthUser) -> Tenant:
    assert_tenant_access(auth, tenant_id)
    tenant = session.query(Tenant).filter(Tenant.id == tenant_id, Tenant.deleted_at.is_(None)).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant
