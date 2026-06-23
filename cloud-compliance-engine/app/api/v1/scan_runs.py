"""Customer-facing scan APIs: list scans, control matrix, batch reprocess."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.config import get_settings
from app.models.compliance import ScanRun, ControlResult, EvaluationRun, Control
from app.schemas.common import ScanRunResponse, ScanControlResultResponse
from app.services.pipeline.process_job import process_job_completed
from app.services.rule_engine.registry import get_registry

router = APIRouter(prefix="/scan-runs", tags=["scan-runs"])


@router.get("", response_model=list[ScanRunResponse])
def list_scan_runs(
    account_id: UUID | None = Query(None),
    framework_id: str = Query("cis_aws_v6"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    """Scan history for customer dashboard."""
    q = db.query(ScanRun).filter(
        ScanRun.tenant_id == UUID(tenant_id),
        ScanRun.framework_id == framework_id,
    )
    if account_id:
        q = q.filter(ScanRun.account_id == account_id)
    rows = q.order_by(ScanRun.started_at.desc()).limit(limit).all()
    return [ScanRunResponse.model_validate(r) for r in rows]


@router.get("/{batch_id}", response_model=ScanRunResponse)
def get_scan_run_by_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    scan_run = db.execute(
        select(ScanRun).where(
            ScanRun.tenant_id == UUID(tenant_id),
            ScanRun.batch_id == batch_id,
        )
    ).scalar_one_or_none()
    if not scan_run:
        raise HTTPException(404, "Scan run not found")
    return ScanRunResponse.model_validate(scan_run)


@router.get("/{batch_id}/controls", response_model=list[ScanControlResultResponse])
def get_scan_control_matrix(
    batch_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    """Control PASS/FAIL matrix for one scan (customer drill-down list)."""
    scan_run = db.execute(
        select(ScanRun).where(
            ScanRun.tenant_id == UUID(tenant_id),
            ScanRun.batch_id == batch_id,
        )
    ).scalar_one_or_none()
    if not scan_run:
        raise HTTPException(404, "Scan run not found")

    run_ids = db.execute(
        select(EvaluationRun.id).where(EvaluationRun.scan_run_id == scan_run.id)
    ).scalars().all()
    if not run_ids:
        return []

    results = db.execute(
        select(ControlResult).where(ControlResult.evaluation_run_id.in_(run_ids))
    ).scalars().all()

    out: list[ScanControlResultResponse] = []
    for r in results:
        catalog = db.execute(
            select(Control).where(
                Control.framework_id == r.framework_id,
                Control.control_id == r.control_id,
            )
        ).scalar_one_or_none()
        details = r.details or {}
        out.append(
            ScanControlResultResponse(
                control_id=r.control_id,
                control_ref=details.get("control_ref") or r.control_id,
                title=details.get("title") or (catalog.title if catalog else None),
                severity=r.severity or (catalog.severity if catalog else None),
                status=r.status,
                message=r.message,
                evidence_count=details.get("evidence_count", 0),
                control_result_id=r.id,
                evaluated_at=r.evaluated_at,
            )
        )
    out.sort(key=lambda x: x.control_id)
    return out


@router.post("/{batch_id}/process")
def reprocess_batch_from_snapshots(
    batch_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Reprocess all snapshots under a batch from execution_results (dev/backfill).
    Reads public.execution_results joined to execution_jobs for batch_id.
    """
    from sqlalchemy import text

    settings = get_settings()
    rows = db.execute(
        text("""
            SELECT ej.id AS execution_job_id, er.snapshot_path, ej.tenant_id, ej.account_id,
                   ej.batch_id, q.extra_metadata
            FROM execution_jobs ej
            JOIN execution_results er ON er.execution_job_id = ej.id
            JOIN queries q ON q.id = ej.query_id
            WHERE ej.batch_id = :batch_id AND ej.tenant_id = :tenant_id AND er.snapshot_path IS NOT NULL
        """),
        {"batch_id": batch_id, "tenant_id": tenant_id},
    ).mappings().all()

    if not rows:
        raise HTTPException(404, "No completed jobs with snapshots for this batch")

    registry = get_registry(db)
    processed = []
    for row in rows:
        meta = row["extra_metadata"] or {}
        if isinstance(meta, str):
            import json
            meta = json.loads(meta)
        event = {
            "execution_job_id": row["execution_job_id"],
            "snapshot_path": row["snapshot_path"],
            "tenant_id": str(row["tenant_id"]),
            "account_id": str(row["account_id"]),
            "batch_id": str(row["batch_id"]),
            "framework_id": meta.get("framework_id", "cis_aws_v6"),
            "control_ref": meta.get("control_ref"),
            "control_id": meta.get("control_id"),
            "category": meta.get("category", "compliance"),
        }
        if event["category"] != "compliance" or not event["control_ref"]:
            continue
        summary = process_job_completed(db, event, registry)
        if summary:
            processed.append(summary)
    return {"batch_id": batch_id, "processed": len(processed), "results": processed}
