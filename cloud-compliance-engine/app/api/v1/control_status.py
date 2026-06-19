"""GET /v1/control-status/latest."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.compliance import ControlState
from app.schemas.common import ControlStatusLatest

router = APIRouter(prefix="/control-status", tags=["control-status"])


@router.get("/latest", response_model=list[ControlStatusLatest])
def get_latest_control_status(
    account_id: UUID = Query(...),
    framework_id: str = Query("cis_aws_v6"),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    rows = db.query(ControlState).filter(
        ControlState.tenant_id == UUID(tenant_id),
        ControlState.account_id == account_id,
        ControlState.framework_id == framework_id,
    ).all()
    return [ControlStatusLatest(
        control_id=r.control_id,
        latest_status=r.latest_status,
        last_evaluated_at=r.last_evaluated_at,
        framework_id=r.framework_id,
    ) for r in rows]
