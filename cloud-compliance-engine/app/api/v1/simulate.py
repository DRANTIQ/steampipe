"""POST /v1/simulate - run evaluation without persisting."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.compliance import Snapshot, ExecutionSnapshotRow
from app.schemas.common import SimulateRequest
from app.services.evaluate import evaluate_zero_rows, build_evidence_and_resources
from app.services.hash_utils import result_hash, rule_definition_hash
from app.services.rule_registry import RuleRegistry, load_rules_from_queries_json

router = APIRouter(prefix="/simulate", tags=["simulate"])


def _get_registry() -> RuleRegistry:
    reg = RuleRegistry()
    base = Path(__file__).resolve().parent.parent.parent.parent
    path = base / "queries" / "cis_v6_queries.json"
    if path.exists():
        reg.load_from_queries_json(path)
    return reg


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
    registry = _get_registry()
    refs = registry.all_control_refs()
    results = []
    for control_ref in refs[:5]:  # limit 5 for simulate
        rule = registry.get(control_ref)
        if not rule:
            continue
        status = evaluate_zero_rows(rows)
        rule_hash = rule.get("rule_definition_hash", rule_definition_hash({
            "control_id": rule.get("control_id"),
            "control_ref": control_ref,
            "pass_rule": rule.get("pass_rule"),
            "required_columns": sorted(rule.get("required_columns") or []),
        }))
        evidence_list, evidence_resources = build_evidence_and_resources(
            rows, rule, control_ref, snapshot.tenant_id, snapshot.account_id,
        )
        res_hash = result_hash({
            "control_id": rule.get("control_id"),
            "control_ref": control_ref,
            "status": status,
            "rule_definition_hash": rule_hash,
            "snapshot_hash": snapshot.snapshot_hash,
        })
        results.append({
            "control_id": rule.get("control_id"),
            "control_ref": control_ref,
            "status": status,
            "rule_definition_hash": rule_hash,
            "result_hash": res_hash,
            "evidence_count": len(evidence_list),
            "evidence_sample": evidence_list[:3],
        })
    return {"snapshot_id": str(body.snapshot_id), "results": results, "persisted": False}
