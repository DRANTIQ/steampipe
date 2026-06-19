"""POST /v1/evaluation-runs, GET /v1/evaluation-runs/{id}."""
from pathlib import Path
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_tenant_id
from app.config import get_settings
from app.models.compliance import EvaluationRun
from app.schemas.common import EvaluationRunCreate
from app.services.extract import extract_snapshot_to_db
from app.services.evaluate import evaluate_snapshot
from app.services.rule_registry import RuleRegistry

router = APIRouter(prefix="/evaluation-runs", tags=["evaluation-runs"])
_rule_registry: RuleRegistry | None = None

def get_rule_registry() -> RuleRegistry:
    global _rule_registry
    if _rule_registry is None:
        _rule_registry = RuleRegistry()
        base = Path(__file__).resolve().parent.parent.parent.parent
        path = base / "queries" / "cis_v6_queries.json"
        if path.exists():
            _rule_registry.load_from_queries_json(path)
    return _rule_registry

@router.post("")
def create_evaluation_run(body: EvaluationRunCreate, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    settings = get_settings()
    tenant_uuid = UUID(tenant_id)
    account_uuid = body.account_id
    if body.snapshot_id:
        registry = get_rule_registry()
        refs = registry.all_control_refs()
        if not refs:
            raise HTTPException(400, "No rules loaded")
        control_ref = refs[0]
        result = evaluate_snapshot(db, body.snapshot_id, control_ref, tenant_uuid, account_uuid, body.framework_id, registry)
        if not result:
            raise HTTPException(404, "Snapshot or rule not found")
        run = db.query(EvaluationRun).filter(EvaluationRun.snapshot_id == body.snapshot_id).order_by(EvaluationRun.created_at.desc()).first()
        return {"evaluation_run_id": str(run.id), "snapshot_id": str(body.snapshot_id)}
    if body.s3_prefix:
        snapshot = extract_snapshot_to_db(db, body.s3_prefix, tenant_uuid, account_uuid, use_local=settings.USE_LOCAL_STORAGE, local_path=settings.LOCAL_STORAGE_PATH, s3_bucket=settings.S3_BUCKET)
        if not snapshot:
            raise HTTPException(400, "Failed to load snapshot from path")
        registry = get_rule_registry()
        refs = registry.all_control_refs()
        control_ref = refs[0] if refs else None
        if not control_ref:
            return {"evaluation_run_id": None, "snapshot_id": str(snapshot.id), "message": "Extract ok; no rules to evaluate"}
        evaluate_snapshot(db, snapshot.id, control_ref, tenant_uuid, account_uuid, body.framework_id, registry)
        run = db.query(EvaluationRun).filter(EvaluationRun.snapshot_id == snapshot.id).order_by(EvaluationRun.created_at.desc()).first()
        return {"evaluation_run_id": str(run.id), "snapshot_id": str(snapshot.id)}
    raise HTTPException(400, "Provide snapshot_id or s3_prefix")

@router.get("/{run_id}")
def get_evaluation_run(run_id: UUID, db: Session = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id, EvaluationRun.tenant_id == UUID(tenant_id)).first()
    if not run:
        raise HTTPException(404, "Evaluation run not found")
    return {"id": str(run.id), "tenant_id": str(run.tenant_id), "account_id": str(run.account_id), "status": run.status, "started_at": run.started_at.isoformat() if run.started_at else None, "finished_at": run.finished_at.isoformat() if run.finished_at else None, "snapshot_id": str(run.snapshot_id) if run.snapshot_id else None}
