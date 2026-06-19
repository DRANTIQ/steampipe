"""Evaluate controls against snapshot rows: zero_rows rule, evidence, control_results."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.compliance import (
    Snapshot,
    ExecutionSnapshotRow,
    EvaluationRun,
    ControlResult,
    ControlEvidenceResource,
    ControlState,
    ComplianceSummary,
)
from app.services.hash_utils import result_hash
from app.services.rule_registry import RuleRegistry

SOURCE_STEAMPIPE = "steampipe"
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"


def _resource_id_from_payload(payload: dict, required_columns: list[str]) -> str:
    for key in ("name", "db_instance_identifier", "instance_id", "account_id", "user_name", "network_acl_id"):
        if key in payload and payload.get(key) is not None:
            return str(payload[key])
    if required_columns and required_columns[0] in payload:
        return str(payload[required_columns[0]])
    return ""


def _key_field_from_payload(payload: dict) -> str:
    for key in ("name", "db_instance_identifier", "account_id", "user_name"):
        if key in payload:
            return key
    return "id"


def _infer_resource_type(control_ref: str) -> str:
    if "s3" in control_ref or "bucket" in control_ref:
        return "s3_bucket"
    if "rds" in control_ref or "db_instance" in control_ref:
        return "rds_instance"
    if "iam" in control_ref or "user" in control_ref:
        return "iam_user"
    if "nacl" in control_ref or "network_acl" in control_ref:
        return "network_acl"
    return "resource"


def evaluate_zero_rows(rows: list[ExecutionSnapshotRow]) -> str:
    """0 rows = PASS, 1+ = FAIL."""
    return STATUS_PASS if len(rows) == 0 else STATUS_FAIL


def build_evidence_and_resources(
    rows: list[ExecutionSnapshotRow],
    rule: dict[str, Any],
    control_ref: str,
    tenant_id: UUID,
    account_id: UUID,
) -> tuple[list[dict], list[dict]]:
    """Build evidence list (for JSONB) and evidence resource dicts (for control_evidence_resources)."""
    required = rule.get("required_columns") or []
    evidence = []
    resources = []
    resource_type = _infer_resource_type(control_ref)
    for r in rows:
        payload = r.payload if isinstance(r.payload, dict) else {}
        res_id = _resource_id_from_payload(payload, required)
        key_f = _key_field_from_payload(payload)
        evidence.append({
            "row_index": len(evidence),
            "resource_id": res_id,
            "fields": {k: payload.get(k) for k in required if k in payload},
        })
        resources.append({
            "tenant_id": tenant_id,
            "account_id": account_id,
            "source": SOURCE_STEAMPIPE,
            "record_id": r.id,
            "resource_type": resource_type,
            "resource_id": res_id or str(r.id),
            "payload_excerpt": {k: payload.get(k) for k in required if k in payload},
        })
    return evidence, resources


def evaluate_snapshot(
    db: Session,
    snapshot_id: str | UUID,
    control_ref: str,
    tenant_id: str | UUID,
    account_id: str | UUID,
    framework_id: str,
    rule_registry: RuleRegistry,
    idempotency_key: str | None = None,
) -> ControlResult | None:
    """
    Run one control (by control_ref) against snapshot rows. Creates evaluation_run, control_result,
    control_evidence_resources; upserts control_state. Returns control_result or None if rule not found.
    """
    rule = rule_registry.get(control_ref)
    if not rule:
        return None

    sid = UUID(str(snapshot_id)) if isinstance(snapshot_id, str) else snapshot_id
    tid = UUID(str(tenant_id)) if isinstance(tenant_id, str) else tenant_id
    aid = UUID(str(account_id)) if isinstance(account_id, str) else account_id

    snapshot = db.get(Snapshot, sid)
    if not snapshot:
        return None

    rows = db.execute(
        select(ExecutionSnapshotRow).where(
            ExecutionSnapshotRow.snapshot_id == sid,
            ExecutionSnapshotRow.source == SOURCE_STEAMPIPE,
        )
    ).scalars().all()

    status = evaluate_zero_rows(rows)
    rule_hash = rule.get("rule_definition_hash", "")
    severity = rule.get("severity")  # may come from controls table; optional

    run = EvaluationRun(
        id=uuid4(),
        tenant_id=tid,
        account_id=aid,
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        snapshot_id=sid,
        idempotency_key=idempotency_key,
    )
    db.add(run)
    db.flush()

    result_payload = {
        "control_id": rule.get("control_id"),
        "control_ref": control_ref,
        "status": status,
        "rule_definition_hash": rule_hash,
        "snapshot_hash": snapshot.snapshot_hash,
    }
    res_hash = result_hash(result_payload)
    prev_hash = None  # TODO: chain from previous result for same account/control

    evidence_list, evidence_resources = build_evidence_and_resources(rows, rule, control_ref, tid, aid)
    summary_msg = f"{len(rows)} violation(s) found" if rows else "No violations"

    result = ControlResult(
        id=uuid4(),
        tenant_id=tid,
        account_id=aid,
        evaluation_run_id=run.id,
        snapshot_id=sid,
        framework_id=framework_id,
        control_id=rule.get("control_id", control_ref),
        status=status,
        severity=severity,
        message=summary_msg,
        rule_definition_hash=rule_hash,
        snapshot_hash=snapshot.snapshot_hash,
        result_hash=res_hash,
        prev_result_hash=prev_hash,
        details={
            "evidence_count": len(evidence_list),
            "pass_rule": "zero_rows",
            "evidence": evidence_list,
            "required_columns": rule.get("required_columns", []),
        },
    )
    db.add(result)
    db.flush()

    for er in evidence_resources:
        er["control_result_id"] = result.id
        db.add(ControlEvidenceResource(**er))

    # Upsert control_state
    stmt = pg_insert(ControlState).values(
        tenant_id=tid,
        account_id=aid,
        framework_id=framework_id,
        control_id=result.control_id,
        latest_control_result_id=result.id,
        latest_status=status,
        last_evaluated_at=result.evaluated_at or datetime.now(timezone.utc),
        last_snapshot_id=sid,
    ).on_conflict_do_update(
        index_elements=["tenant_id", "account_id", "framework_id", "control_id"],
        set_={
            "latest_control_result_id": result.id,
            "latest_status": status,
            "last_evaluated_at": result.evaluated_at,
            "last_snapshot_id": sid,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    db.execute(stmt)

    # Compliance summary for this run
    pass_c = 1 if status == STATUS_PASS else 0
    fail_c = 1 if status == STATUS_FAIL else 0
    db.add(ComplianceSummary(
        tenant_id=tid,
        account_id=aid,
        framework_id=framework_id,
        evaluation_run_id=run.id,
        pass_count=pass_c,
        fail_count=fail_c,
        unknown_count=0,
    ))
    db.flush()
    return result
