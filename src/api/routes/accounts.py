from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import DbSession
from src.api.schemas import CloudAccountCreate, CloudAccountResponse
from src.models import CloudAccount, Tenant

router = APIRouter()


@router.post("", response_model=CloudAccountResponse)
def create_account(session: DbSession, tenant_id: str, body: CloudAccountCreate) -> CloudAccount:
    tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    existing = (
        session.query(CloudAccount)
        .filter(
            CloudAccount.tenant_id == tenant_id,
            CloudAccount.provider == body.provider,
            CloudAccount.account_id == body.account_id,
            CloudAccount.deleted_at.is_(None),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists for this tenant/provider/account_id")
    acc = CloudAccount(
        id=str(uuid4()),
        tenant_id=tenant_id,
        provider=body.provider,
        account_id=body.account_id,
        region=body.region,
        name=body.name,
        secret_arn=body.secret_arn,
        extra_metadata=body.extra_metadata,
    )
    session.add(acc)
    session.flush()
    return acc


@router.get("", response_model=list[CloudAccountResponse])
def list_accounts(
    session: DbSession,
    tenant_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    active: bool | None = None,
) -> list[CloudAccount]:
    q = session.query(CloudAccount).filter(CloudAccount.tenant_id == tenant_id, CloudAccount.deleted_at.is_(None))
    if active is not None:
        q = q.filter(CloudAccount.active == active)
    return q.offset(skip).limit(limit).all()
