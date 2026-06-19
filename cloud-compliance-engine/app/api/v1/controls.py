"""GET /v1/controls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.compliance import Control

router = APIRouter(prefix="/controls", tags=["controls"])


@router.get("", response_model=list[dict])
def list_controls(
    framework_id: str | None = Query(None),
    provider: str | None = Query(None, description="aws | azure | gcp"),
    category: str | None = Query(None, description="compliance | cost_optimization | ..."),
    severity: str | None = Query(None),
    enabled: bool | None = Query(None),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    q = db.query(Control)
    if framework_id:
        q = q.filter(Control.framework_id == framework_id)
    if provider:
        q = q.filter(Control.provider == provider)
    if category:
        q = q.filter(Control.category == category)
    if severity:
        q = q.filter(Control.severity == severity)
    if enabled is not None:
        q = q.filter(Control.enabled == enabled)
    rows = q.all()
    return [
        {
            "id": str(r.id),
            "control_id": r.control_id,
            "framework_id": r.framework_id,
            "provider": r.provider,
            "category": r.category,
            "title": r.title,
            "severity": r.severity,
            "remediation": r.remediation,
            "enabled": r.enabled,
        }
        for r in rows
    ]
