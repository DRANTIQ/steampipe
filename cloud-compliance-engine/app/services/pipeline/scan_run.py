"""Scan run lifecycle: one scan = one execution batch."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.compliance import ScanRun, ComplianceSummary, ControlResult, EvaluationRun
from app.services.rule_engine.registry import RuleRegistry

SCAN_STATUS_RUNNING = "running"
SCAN_STATUS_COMPLETED = "completed"
SCAN_STATUS_FAILED = "failed"


def get_or_create_scan_run(
    db: Session,
    *,
    tenant_id: UUID,
    account_id: UUID,
    batch_id: str,
    framework_id: str,
    rule_registry: RuleRegistry,
) -> ScanRun:
    existing = db.execute(
        select(ScanRun).where(
            ScanRun.tenant_id == tenant_id,
            ScanRun.batch_id == batch_id,
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    batch_total = db.execute(
        text("SELECT total_jobs FROM execution_batches WHERE id = :batch_id"),
        {"batch_id": batch_id},
    ).scalar()
    total = int(batch_total) if batch_total else rule_registry.automated_control_count()
    scan_run = ScanRun(
        id=uuid4(),
        tenant_id=tenant_id,
        account_id=account_id,
        batch_id=batch_id,
        framework_id=framework_id,
        status=SCAN_STATUS_RUNNING,
        total_controls=total,
        started_at=datetime.now(timezone.utc),
    )
    db.add(scan_run)
    db.flush()
    return scan_run


def record_control_evaluated(db: Session, scan_run: ScanRun, status: str) -> ScanRun:
    scan_run.evaluated_controls += 1
    if status == "PASS":
        scan_run.pass_count += 1
    elif status == "FAIL":
        scan_run.fail_count += 1
    else:
        scan_run.unknown_count += 1
    db.flush()
    return scan_run


def maybe_finalize_scan_run(db: Session, scan_run: ScanRun) -> ScanRun:
    if scan_run.status == SCAN_STATUS_COMPLETED:
        return scan_run
    if scan_run.evaluated_controls < scan_run.total_controls:
        return scan_run

    evaluated = scan_run.pass_count + scan_run.fail_count + scan_run.unknown_count
    scan_run.score_pct = round((scan_run.pass_count / evaluated) * 100, 2) if evaluated else 0
    scan_run.status = SCAN_STATUS_COMPLETED
    scan_run.finished_at = datetime.now(timezone.utc)

    db.add(
        ComplianceSummary(
            tenant_id=scan_run.tenant_id,
            account_id=scan_run.account_id,
            framework_id=scan_run.framework_id,
            scan_run_id=scan_run.id,
            pass_count=scan_run.pass_count,
            fail_count=scan_run.fail_count,
            unknown_count=scan_run.unknown_count,
            score_total=scan_run.score_pct,
            severity_breakdown=_severity_breakdown(db, scan_run),
        )
    )
    db.flush()
    return scan_run


def _severity_breakdown(db: Session, scan_run: ScanRun) -> dict:
    """Aggregate fail counts by severity for scan-level summary."""
    results = db.execute(
        select(ControlResult).where(
            ControlResult.tenant_id == scan_run.tenant_id,
            ControlResult.account_id == scan_run.account_id,
            ControlResult.framework_id == scan_run.framework_id,
            ControlResult.evaluation_run_id.in_(
                select(EvaluationRun.id).where(EvaluationRun.scan_run_id == scan_run.id)
            ),
        )
    ).scalars().all()
    breakdown: dict[str, int] = {}
    for r in results:
        if r.status != "FAIL":
            continue
        sev = r.severity or "Unknown"
        breakdown[sev] = breakdown.get(sev, 0) + 1
    return breakdown
