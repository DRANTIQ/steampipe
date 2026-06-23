"""POST /v1/evaluation-runs, GET /v1/evaluation-runs/{id}."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.config import get_settings
from app.models.compliance import EvaluationRun, Snapshot
from app.schemas.common import EvaluationRunCreate
from app.services.evaluate import evaluate_snapshot
from app.services.extract import extract_snapshot_to_db
from app.services.pipeline.scan_run import get_or_create_scan_run, maybe_finalize_scan_run, record_control_evaluated
from app.services.rule_engine.registry import get_registry

router = APIRouter(prefix="/evaluation-runs", tags=["evaluation-runs"])


@router.post("")
def create_evaluation_run(
    body: EvaluationRunCreate,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    settings = get_settings()
    tenant_uuid = UUID(tenant_id)
    account_uuid = body.account_id
    registry = get_registry(db)

    snapshot: Snapshot | None = None
    if body.s3_prefix:
        snapshot = extract_snapshot_to_db(
            db,
            body.s3_prefix,
            tenant_uuid,
            account_uuid,
            use_local=settings.USE_LOCAL_STORAGE,
            local_path=settings.LOCAL_STORAGE_PATH,
            s3_bucket=settings.S3_BUCKET,
        )
        if not snapshot:
            raise HTTPException(400, "Failed to load snapshot from path")
    elif body.snapshot_id:
        snapshot = db.get(Snapshot, body.snapshot_id)
        if not snapshot or snapshot.tenant_id != tenant_uuid:
            raise HTTPException(404, "Snapshot not found")

    if not snapshot:
        raise HTTPException(400, "Provide snapshot_id or s3_prefix")

    control_ref = body.control_ref or snapshot.control_ref
    if not control_ref:
        raise HTTPException(400, "control_ref required (not on snapshot metadata)")

    scan_run = None
    if snapshot.batch_id:
        scan_run = get_or_create_scan_run(
            db,
            tenant_id=tenant_uuid,
            account_id=account_uuid,
            batch_id=snapshot.batch_id,
            framework_id=body.framework_id,
            rule_registry=registry,
        )

    result = evaluate_snapshot(
        db,
        snapshot.id,
        control_ref,
        tenant_uuid,
        account_uuid,
        body.framework_id,
        registry,
        scan_run_id=scan_run.id if scan_run else None,
    )
    if not result:
        raise HTTPException(404, "Rule not found for control_ref")

    if scan_run:
        record_control_evaluated(db, scan_run, result.status)
        maybe_finalize_scan_run(db, scan_run)

    run = db.query(EvaluationRun).filter(EvaluationRun.snapshot_id == snapshot.id).order_by(
        EvaluationRun.created_at.desc()
    ).first()
    return {
        "evaluation_run_id": str(run.id) if run else None,
        "snapshot_id": str(snapshot.id),
        "control_ref": control_ref,
        "status": result.status,
        "scan_run_id": str(scan_run.id) if scan_run else None,
    }


@router.get("/{run_id}")
def get_evaluation_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    run = db.query(EvaluationRun).filter(
        EvaluationRun.id == run_id,
        EvaluationRun.tenant_id == UUID(tenant_id),
    ).first()
    if not run:
        raise HTTPException(404, "Evaluation run not found")
    return {
        "id": str(run.id),
        "tenant_id": str(run.tenant_id),
        "account_id": str(run.account_id),
        "status": run.status,
        "framework_id": run.framework_id,
        "control_ref": run.control_ref,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "snapshot_id": str(run.snapshot_id) if run.snapshot_id else None,
        "scan_run_id": str(run.scan_run_id) if run.scan_run_id else None,
        "rule_version_id": str(run.rule_version_id) if run.rule_version_id else None,
        "framework_version_id": str(run.framework_version_id) if run.framework_version_id else None,
    }
