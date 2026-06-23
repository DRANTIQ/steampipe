"""Process Stage 1 job.completed events: extract → evaluate → scan progress."""
from __future__ import annotations

import logging
from uuid import UUID
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.extract import extract_snapshot_to_db
from app.services.evaluate import evaluate_snapshot
from app.services.pipeline.scan_run import (
    get_or_create_scan_run,
    maybe_finalize_scan_run,
    record_control_evaluated,
)
from app.services.rule_engine.catalog import load_compliance_rules_from_metadata
from app.services.rule_engine.registry import CIS_AWS_V6_FRAMEWORK_ID, get_registry

logger = logging.getLogger(__name__)


def process_job_completed(
    db: Session,
    event: dict[str, Any],
    rule_registry=None,
) -> dict[str, Any] | None:
    """Handle one steampipe:job_completed message."""
    if event.get("category") != "compliance":
        return None

    snapshot_path = event.get("snapshot_path")
    tenant_id = event.get("tenant_id")
    account_id = event.get("account_id")
    batch_id = event.get("batch_id")
    control_ref = event.get("control_ref")
    framework_id = event.get("framework_id") or CIS_AWS_V6_FRAMEWORK_ID
    execution_job_id = event.get("execution_job_id")

    if not all([snapshot_path, tenant_id, account_id, control_ref]):
        logger.warning("Incomplete job.completed event: %s", event)
        return None

    registry = rule_registry or get_registry(db, framework_id)
    if not registry.get(control_ref):
        meta_rule = load_compliance_rules_from_metadata(
            {
                "control_ref": control_ref,
                "control_id": event.get("control_id"),
                "framework_id": framework_id,
                "pass_rule": "zero_rows",
            }
        )
        if meta_rule:
            registry.register_ephemeral(meta_rule)

    settings = get_settings()
    tid = UUID(str(tenant_id))
    aid = UUID(str(account_id))

    scan_run = None
    if batch_id:
        scan_run = get_or_create_scan_run(
            db,
            tenant_id=tid,
            account_id=aid,
            batch_id=str(batch_id),
            framework_id=framework_id,
            rule_registry=registry,
        )

    snapshot = extract_snapshot_to_db(
        db,
        snapshot_path,
        tid,
        aid,
        execution_job_id=execution_job_id,
        scan_run_id=scan_run.id if scan_run else None,
        metadata={
            "batch_id": batch_id,
            "framework_id": framework_id,
            "control_ref": control_ref,
            "control_id": event.get("control_id"),
            "query_id": event.get("query_id"),
            "pass_rule": event.get("pass_rule"),
            "required_columns": event.get("required_columns"),
        },
        use_local=settings.USE_LOCAL_STORAGE,
        local_path=settings.LOCAL_STORAGE_PATH,
        s3_bucket=settings.S3_BUCKET,
    )
    if not snapshot:
        logger.error("Extract failed path=%s job=%s", snapshot_path, execution_job_id)
        return None

    idempotency_key = None
    result = evaluate_snapshot(
        db,
        snapshot.id,
        control_ref,
        tid,
        aid,
        framework_id,
        registry,
        scan_run_id=scan_run.id if scan_run else None,
        idempotency_key=idempotency_key,
    )
    if not result:
        logger.error("Evaluate failed snapshot=%s control_ref=%s", snapshot.id, control_ref)
        return None

    if scan_run:
        record_control_evaluated(db, scan_run, result.status)
        maybe_finalize_scan_run(db, scan_run)

    return {
        "execution_job_id": execution_job_id,
        "snapshot_id": str(snapshot.id),
        "control_ref": control_ref,
        "status": result.status,
        "scan_run_id": str(scan_run.id) if scan_run else None,
        "scan_status": scan_run.status if scan_run else None,
    }
