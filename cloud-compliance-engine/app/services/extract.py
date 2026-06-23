"""Extract Bronze snapshot JSON into compliance Silver layer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.compliance import Snapshot, ExecutionSnapshotRow
from app.services.hash_utils import record_hash, snapshot_hash_from_record_hashes
from app.services.rule_engine.catalog import build_pinned_rule_metadata

SOURCE_STEAMPIPE = "steampipe"
RECORD_TYPE_STEAMPIPE_ROW = "steampipe_row"


def _resolve_local_snapshot_path(snapshot_path: str, local_path: str) -> Path:
    """Resolve snapshot_path from execution_results to a readable file path."""
    rel = snapshot_path.lstrip("./")
    base = Path(local_path).resolve()
    if rel.startswith("local/snapshots/"):
        repo_root = base.parent.parent
        return repo_root / rel
    candidate = base / rel
    if candidate.exists():
        return candidate
    return Path(snapshot_path)


def get_snapshot_content(snapshot_path: str, use_local: bool, local_path: str, s3_bucket: str) -> dict[str, Any] | None:
    if not snapshot_path:
        return None
    if snapshot_path.startswith("s3://"):
        try:
            import boto3
            parts = snapshot_path[5:].split("/", 1)
            bucket, key = parts[0], parts[1]
            client = boto3.client("s3")
            resp = client.get_object(Bucket=bucket, Key=key)
            return json.loads(resp["Body"].read().decode("utf-8"))
        except Exception:
            return None
    try:
        path = _resolve_local_snapshot_path(snapshot_path, local_path)
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _find_existing_snapshot(db: Session, execution_job_id: str | None) -> Snapshot | None:
    if not execution_job_id:
        return None
    return db.execute(
        select(Snapshot).where(Snapshot.execution_job_id == execution_job_id)
    ).scalar_one_or_none()


def extract_snapshot_to_db(
    db: Session,
    snapshot_path: str,
    tenant_id: str | UUID,
    account_id: str | UUID,
    snapshot_time: datetime | None = None,
    execution_job_id: str | None = None,
    scan_run_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    use_local: bool = False,
    local_path: str = "./local/snapshots",
    s3_bucket: str = "",
) -> Snapshot | None:
    """Load Bronze JSON → compliance.snapshots + execution_snapshot_rows (idempotent by execution_job_id)."""
    meta = metadata or {}
    content = get_snapshot_content(snapshot_path, use_local, local_path, s3_bucket)
    if not content:
        return None

    rows = content.get("rows")
    if rows is None and isinstance(content, list):
        rows = content
    if rows is None:
        rows = []

    snapshot_meta = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
    merged = {**snapshot_meta, **meta}
    if not execution_job_id and merged.get("execution_job_id"):
        execution_job_id = str(merged["execution_job_id"])

    existing = _find_existing_snapshot(db, execution_job_id)
    if existing:
        return existing

    tid = UUID(str(tenant_id)) if isinstance(tenant_id, str) else tenant_id
    aid = UUID(str(account_id)) if isinstance(account_id, str) else account_id
    captured = merged.get("captured_at")
    if isinstance(captured, str):
        try:
            now = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError:
            now = snapshot_time or datetime.now(timezone.utc)
    else:
        now = snapshot_time or datetime.now(timezone.utc)

    snapshot = Snapshot(
        id=uuid4(),
        tenant_id=tid,
        account_id=aid,
        snapshot_time=now,
        sources=[SOURCE_STEAMPIPE],
        s3_prefix=snapshot_path,
        snapshot_hash="",
        record_count=0,
        execution_job_id=execution_job_id,
        batch_id=str(merged["batch_id"]) if merged.get("batch_id") else None,
        framework_id=merged.get("framework_id"),
        control_ref=merged.get("control_ref"),
        control_id=merged.get("control_id"),
        query_id=str(merged["query_id"]) if merged.get("query_id") else None,
        query_name=merged.get("query_name"),
        scan_run_id=scan_run_id,
        rule_metadata=build_pinned_rule_metadata(merged) if merged.get("control_ref") else None,
    )
    db.add(snapshot)
    db.flush()

    record_hashes_list: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rh = record_hash(row)
        record_hashes_list.append(rh)
        stmt = insert(ExecutionSnapshotRow).values(
            tenant_id=tid,
            account_id=aid,
            snapshot_id=snapshot.id,
            source=SOURCE_STEAMPIPE,
            record_type=RECORD_TYPE_STEAMPIPE_ROW,
            record_hash=rh,
            payload=row,
            region=str(row.get("region")) if row.get("region") else None,
            natural_key=merged.get("natural_key"),
        ).on_conflict_do_nothing(index_elements=["snapshot_id", "record_hash"])
        db.execute(stmt)

    snapshot.snapshot_hash = snapshot_hash_from_record_hashes(record_hashes_list)
    snapshot.record_count = len(record_hashes_list)
    db.flush()
    return snapshot
