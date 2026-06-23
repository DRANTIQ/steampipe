"""POST /v1/simulate - run evaluation without persisting."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.compliance import Snapshot, ExecutionSnapshotRow
from app.schemas.common import SimulateRequest
from app.services.hash_utils import result_hash, rule_definition_hash
from app.services.rule_engine.engine import apply_pass_rule, build_evidence_entries
from app.services.rule_engine.registry import get_registry
from app.services.rule_engine.resolve import resolve_evaluation_rule

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("", response_model=dict)
def simulate(
    body: SimulateRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    """Run evaluation in-memory; do not persist control_results or control_state."""
    snapshot = db.query(Snapshot).filter(
        Snapshot.id == body.snapshot_id,
        Snapshot.tenant_id == UUID(tenant_id),
    ).first()
    if not snapshot:
        raise HTTPException(404, "Snapshot not found")
    rows = db.query(ExecutionSnapshotRow).filter(
        ExecutionSnapshotRow.snapshot_id == body.snapshot_id,
    ).all()
    registry = get_registry(db)
    framework_id = snapshot.framework_id or "cis_aws_v6"
    control_ref = snapshot.control_ref
    if not control_ref:
        raise HTTPException(400, "No control_ref on snapshot")
    resolved = resolve_evaluation_rule(db, snapshot, control_ref, framework_id, registry)
    if not resolved:
        raise HTTPException(404, f"No rule for control_ref={control_ref}")
    rule = resolved.rule
    control_ref = rule.get("control_ref") or control_ref

    pass_rule = rule.get("pass_rule") or "zero_rows"
    status = apply_pass_rule(pass_rule, len(rows))
    rule_hash = rule.get("rule_definition_hash", rule_definition_hash({
        "control_id": rule.get("control_id"),
        "control_ref": control_ref,
        "pass_rule": pass_rule,
        "required_columns": sorted(rule.get("required_columns") or []),
    }))
    evidence_list, _, _ = build_evidence_entries(rows, rule.get("required_columns") or [], control_ref)
    res_hash = result_hash({
        "control_id": rule.get("control_id"),
        "control_ref": control_ref,
        "status": status,
        "rule_definition_hash": rule_hash,
        "snapshot_hash": snapshot.snapshot_hash,
    })
    return {
        "snapshot_id": str(body.snapshot_id),
        "control_ref": control_ref,
        "status": status,
        "rule_definition_hash": rule_hash,
        "result_hash": res_hash,
        "evidence_count": len(evidence_list),
        "evidence_sample": evidence_list[:5],
        "rule_source": resolved.rule_source,
        "persisted": False,
    }
