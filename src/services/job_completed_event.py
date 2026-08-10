"""Build steampipe:job_completed Redis payloads for compliance worker."""
from __future__ import annotations

from typing import Any


def build_job_completed_payload(
    *,
    job_id: str,
    snapshot_path: str | None,
    tenant_id: str,
    account_id: str,
    query_id: str,
    batch_id: str | None,
    extra_metadata: dict[str, Any] | None,
    row_count: int,
) -> dict[str, Any]:
    meta = extra_metadata if isinstance(extra_metadata, dict) else {}
    payload: dict[str, Any] = {
        "execution_job_id": job_id,
        "snapshot_path": snapshot_path,
        "tenant_id": tenant_id,
        "account_id": account_id,
        "query_id": query_id,
        "batch_id": batch_id,
        "control_ref": meta.get("control_ref"),
        "control_id": meta.get("control_id"),
        "framework_id": meta.get("framework_id"),
        "category": meta.get("category"),
        "row_count": row_count,
    }
    if meta.get("pass_rule"):
        payload["pass_rule"] = meta.get("pass_rule")
    required = meta.get("required_columns")
    if isinstance(required, list) and required:
        payload["required_columns"] = [str(c) for c in required]
    if meta.get("natural_key"):
        payload["natural_key"] = meta.get("natural_key")
    return payload
