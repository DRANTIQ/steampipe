"""POST /v1/snapshots/ingest — trigger snapshot JSON → Postgres (extract only, no evaluation)."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_tenant_id
from app.config import get_settings
from app.schemas.common import IngestSnapshotRequest
from app.services.extract import extract_snapshot_to_db

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.post("/ingest")
def ingest_snapshot(
    body: IngestSnapshotRequest,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Load snapshot JSON from snapshot_path (S3 or local) into Postgres.
    Creates compliance.snapshots + compliance.execution_snapshot_rows. Does not run evaluation.
    Use this to trigger "snapshots to Postgres" on demand.
    """
    settings = get_settings()
    tenant_uuid = UUID(tenant_id)
    snapshot = extract_snapshot_to_db(
        db,
        body.snapshot_path,
        tenant_uuid,
        body.account_id,
        execution_job_id=body.execution_job_id,
        use_local=settings.USE_LOCAL_STORAGE,
        local_path=settings.LOCAL_STORAGE_PATH,
        s3_bucket=settings.S3_BUCKET,
    )
    if not snapshot:
        raise HTTPException(400, "Failed to load snapshot from path (check path and credentials)")
    return {
        "snapshot_id": str(snapshot.id),
        "record_count": snapshot.record_count,
        "snapshot_hash": snapshot.snapshot_hash,
        "message": "Snapshot ingested. Call POST /v1/evaluation-runs with this snapshot_id to evaluate.",
    }
