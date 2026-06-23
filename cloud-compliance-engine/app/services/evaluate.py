"""Evaluate controls against Silver snapshot rows."""
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
    Control,
)
from app.services.hash_utils import result_hash
from app.services.rule_engine.engine import (
    STATUS_UNKNOWN,
    apply_pass_rule,
    build_evidence_entries,
)
from app.services.rule_engine.registry import RuleRegistry
from app.services.rule_engine.resolve import resolve_evaluation_rule

SOURCE_STEAMPIPE = "steampipe"


def _lookup_control(db: Session, framework_id: str, control_id: str) -> Control | None:
    return db.execute(
        select(Control).where(
            Control.framework_id == framework_id,
            Control.control_id == control_id,
        )
    ).scalar_one_or_none()


def evaluate_snapshot(
    db: Session,
    snapshot_id: str | UUID,
    control_ref: str,
    tenant_id: str | UUID,
    account_id: str | UUID,
    framework_id: str,
    rule_registry: RuleRegistry,
    scan_run_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> ControlResult | None:
    """Run one control against snapshot rows; persist Gold layer artifacts."""
    sid = UUID(str(snapshot_id)) if isinstance(snapshot_id, str) else snapshot_id
    tid = UUID(str(tenant_id)) if isinstance(tenant_id, str) else tenant_id
    aid = UUID(str(account_id)) if isinstance(account_id, str) else account_id

    snapshot = db.get(Snapshot, sid)
    if not snapshot:
        return None

    resolved = resolve_evaluation_rule(db, snapshot, control_ref, framework_id, rule_registry)
    if not resolved:
        return None
    rule = resolved.rule

    rule_hash = rule.get("rule_definition_hash", "")
    effective_idempotency_key = idempotency_key
    if not effective_idempotency_key and snapshot.execution_job_id:
        effective_idempotency_key = f"{snapshot.execution_job_id}:{control_ref}:{rule_hash}"

    if effective_idempotency_key:
        existing_run = db.execute(
            select(EvaluationRun).where(EvaluationRun.idempotency_key == effective_idempotency_key)
        ).scalar_one_or_none()
        if existing_run:
            return db.execute(
                select(ControlResult).where(ControlResult.evaluation_run_id == existing_run.id)
            ).scalar_one_or_none()

    rows = db.execute(
        select(ExecutionSnapshotRow).where(
            ExecutionSnapshotRow.snapshot_id == sid,
            ExecutionSnapshotRow.source == SOURCE_STEAMPIPE,
        )
    ).scalars().all()

    pass_rule = rule.get("pass_rule") or "zero_rows"
    status = apply_pass_rule(pass_rule, len(rows))
    control_id = rule.get("control_id") or control_ref
    catalog_control = _lookup_control(db, framework_id, control_id)
    severity = catalog_control.severity if catalog_control else rule.get("severity")
    title = catalog_control.title if catalog_control else None
    remediation = catalog_control.remediation if catalog_control else None

    run = EvaluationRun(
        id=uuid4(),
        tenant_id=tid,
        account_id=aid,
        status="succeeded",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        snapshot_id=sid,
        scan_run_id=scan_run_id,
        framework_id=framework_id,
        framework_version_id=resolved.framework_version_id,
        rule_version_id=resolved.rule_version_id,
        control_ref=control_ref,
        idempotency_key=effective_idempotency_key,
    )
    db.add(run)
    db.flush()

    evidence_list, evidence_resources, _ = build_evidence_entries(
        rows, rule.get("required_columns") or [], control_ref
    )
    summary_msg = f"{len(rows)} violation(s) found" if rows else "No violations"

    result_payload = {
        "control_id": control_id,
        "control_ref": control_ref,
        "status": status,
        "rule_definition_hash": rule_hash,
        "snapshot_hash": snapshot.snapshot_hash,
    }
    res_hash = result_hash(result_payload)

    result = ControlResult(
        id=uuid4(),
        tenant_id=tid,
        account_id=aid,
        evaluation_run_id=run.id,
        snapshot_id=sid,
        framework_id=framework_id,
        control_id=control_id,
        status=status,
        severity=severity,
        message=summary_msg,
        rule_definition_hash=rule_hash,
        snapshot_hash=snapshot.snapshot_hash,
        result_hash=res_hash,
        details={
            "control_ref": control_ref,
            "title": title,
            "remediation": remediation,
            "evidence_count": len(evidence_list),
            "pass_rule": pass_rule,
            "rule_source": resolved.rule_source,
            "rule_version_id": str(resolved.rule_version_id) if resolved.rule_version_id else None,
            "framework_version_id": str(resolved.framework_version_id) if resolved.framework_version_id else None,
            "evidence": evidence_list,
            "required_columns": rule.get("required_columns") or [],
        },
    )
    db.add(result)
    db.flush()

    for er in evidence_resources:
        db.add(
            ControlEvidenceResource(
                tenant_id=tid,
                account_id=aid,
                control_result_id=result.id,
                source=er["source"],
                record_id=er.get("record_id"),
                resource_type=er["resource_type"],
                resource_id=er["resource_id"],
                payload_excerpt=er.get("payload_excerpt"),
            )
        )

    stmt = pg_insert(ControlState).values(
        tenant_id=tid,
        account_id=aid,
        framework_id=framework_id,
        control_id=control_id,
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

    pass_c = 1 if status == "PASS" else 0
    fail_c = 1 if status == "FAIL" else 0
    unknown_c = 1 if status == STATUS_UNKNOWN else 0
    db.add(
        ComplianceSummary(
            tenant_id=tid,
            account_id=aid,
            framework_id=framework_id,
            evaluation_run_id=run.id,
            scan_run_id=scan_run_id,
            pass_count=pass_c,
            fail_count=fail_c,
            unknown_count=unknown_c,
        )
    )
    db.flush()
    return result
