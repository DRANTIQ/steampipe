"""Extract snapshot JSON from S3 or local path into compliance.snapshots + execution_snapshot_rows."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.compliance import Snapshot, ExecutionSnapshotRow
from app.services.hash_utils import record_hash, snapshot_hash_from_record_hashes

SOURCE_STEAMPIPE = "steampipe"
RECORD_TYPE_STEAMPIPE_ROW = "steampipe_row"


def get_snapshot_content(snapshot_path: str, use_local: bool, local_path: str, s3_bucket: str) -> dict[str, Any] | None:
    """Load JSON from snapshot_path (s3://bucket/key or local path)."""
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
        return json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_snapshot_to_db(
    db: Session,
    snapshot_path: str,
    tenant_id: str | UUID,
    account_id: str | UUID,
    snapshot_time: datetime | None = None,
    execution_job_id: str | None = None,
    use_local: bool = False,
    local_path: str = "./local/snapshots",
    s3_bucket: str = "",
) -> Snapshot | None:
    """
    Load snapshot JSON from snapshot_path, create compliance.snapshots row and
    compliance.execution_snapshot_rows. Returns the Snapshot model or None if load failed.
    """
    content = get_snapshot_content(snapshot_path, use_local, local_path, s3_bucket)
    if not content:
        return None

    rows = content.get("rows")
    if rows is None and isinstance(content, list):
        rows = content
    if rows is None:
        rows = []

    snapshot_meta = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
    if not execution_job_id and snapshot_meta.get("execution_job_id"):
        execution_job_id = str(snapshot_meta["execution_job_id"])

    tid = UUID(str(tenant_id)) if isinstance(tenant_id, str) else tenant_id
    aid = UUID(str(account_id)) if isinstance(account_id, str) else account_id
    now = snapshot_time or datetime.now(timezone.utc)

    snapshot = Snapshot(
        id=uuid4(),
        tenant_id=tid,
        account_id=aid,
        snapshot_time=now,
        sources=[SOURCE_STEAMPIPE],
        s3_prefix=snapshot_path if not snapshot_path.startswith("s3://") else None,
        snapshot_hash="",  # set after we have record_hashes
        record_count=0,
        execution_job_id=execution_job_id,
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
        ).on_conflict_do_nothing(index_elements=["snapshot_id", "record_hash"])
        db.execute(stmt)

    snapshot.snapshot_hash = snapshot_hash_from_record_hashes(record_hashes_list)
    snapshot.record_count = len(record_hashes_list)
    db.flush()
    return snapshot
