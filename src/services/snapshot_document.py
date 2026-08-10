"""Build canonical snapshot JSON documents (metadata + Steampipe rows)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def infer_natural_key(required_columns: list[str] | None) -> str:
    """Pick the best resource identifier column for evidence / dedup."""
    if not required_columns:
        return "id"
    priority = (
        "name",
        "db_instance_identifier",
        "instance_id",
        "account_id",
        "user_name",
        "network_acl_id",
        "group_id",
        "access_key_id",
        "file_system_id",
        "vpc_id",
        "region",
    )
    for key in priority:
        if key in required_columns:
            return key
    return required_columns[0]


def normalize_steampipe_output(output: dict[str, Any] | list[Any]) -> tuple[list[Any], list[dict[str, Any]] | None]:
    """Return (rows, columns) from Steampipe JSON output."""
    if isinstance(output, list):
        return output, None
    if isinstance(output, dict):
        rows = output.get("rows")
        if rows is None and "columns" not in output and "metadata" not in output:
            return [], None
        if rows is None:
            rows = []
        columns = output.get("columns")
        return rows if isinstance(rows, list) else [], columns if isinstance(columns, list) else None
    return [], None


def build_snapshot_document(
    *,
    steampipe_output: dict[str, Any] | list[Any],
    execution_job_id: str,
    query_id: str,
    query_name: str,
    tenant_id: str,
    account_id: str,
    provider: str,
    batch_id: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Wrap Steampipe output with lineage metadata for Bronze layer snapshots."""
    rows, columns = normalize_steampipe_output(steampipe_output)
    meta = extra_metadata or {}
    required = meta.get("required_columns") or []
    if isinstance(required, list):
        required_columns = [str(c) for c in required]
    else:
        required_columns = []

    natural_key = meta.get("natural_key") or infer_natural_key(required_columns)

    metadata: dict[str, Any] = {
        "execution_job_id": execution_job_id,
        "query_id": query_id,
        "query_name": query_name,
        "tenant_id": tenant_id,
        "account_id": account_id,
        "provider": provider,
        "category": meta.get("category"),
        "framework_id": meta.get("framework_id"),
        "framework": meta.get("framework"),
        "control_id": meta.get("control_id"),
        "control_ref": meta.get("control_ref"),
        "pass_rule": meta.get("pass_rule"),
        "required_columns": required_columns,
        "natural_key": natural_key,
        "batch_id": batch_id,
        "row_count": len(rows),
        "captured_at": (captured_at or datetime.now(timezone.utc)).isoformat(),
        "schema_version": "1.0",
    }
    doc: dict[str, Any] = {"metadata": metadata, "rows": rows}
    if columns is not None:
        doc["columns"] = columns
    return doc
