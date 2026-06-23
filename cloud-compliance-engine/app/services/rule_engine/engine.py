"""Pass-rule evaluation engine for compliance checks."""
from __future__ import annotations

from typing import Any

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_UNKNOWN = "UNKNOWN"

SUPPORTED_PASS_RULES = frozenset({"zero_rows", "non_zero_rows"})


def apply_pass_rule(pass_rule: str, row_count: int) -> str:
    """Evaluate a snapshot row count against a pass rule."""
    rule = (pass_rule or "zero_rows").strip().lower()
    if rule == "zero_rows":
        return STATUS_PASS if row_count == 0 else STATUS_FAIL
    if rule == "non_zero_rows":
        return STATUS_PASS if row_count > 0 else STATUS_FAIL
    return STATUS_UNKNOWN


def build_evidence_entries(
    rows: list[Any],
    required_columns: list[str],
    control_ref: str,
) -> tuple[list[dict], list[dict], str]:
    """Build evidence list and resource dicts from snapshot row payloads."""
    evidence: list[dict] = []
    resources: list[dict] = []
    resource_type = _infer_resource_type(control_ref)
    for idx, row in enumerate(rows):
        payload = row.payload if hasattr(row, "payload") and isinstance(row.payload, dict) else (row if isinstance(row, dict) else {})
        res_id = _resource_id_from_payload(payload, required_columns)
        excerpt = {k: payload.get(k) for k in required_columns if k in payload}
        evidence.append({"row_index": idx, "resource_id": res_id, "fields": excerpt})
        resources.append(
            {
                "source": "steampipe",
                "record_id": getattr(row, "id", None),
                "resource_type": resource_type,
                "resource_id": res_id or str(getattr(row, "id", idx)),
                "payload_excerpt": excerpt,
            }
        )
    return evidence, resources, resource_type


def _resource_id_from_payload(payload: dict, required_columns: list[str]) -> str:
    for key in (
        "name",
        "db_instance_identifier",
        "instance_id",
        "account_id",
        "user_name",
        "network_acl_id",
        "bucket_name",
        "arn",
    ):
        if key in payload and payload.get(key) is not None:
            return str(payload[key])
    if required_columns and required_columns[0] in payload:
        return str(payload[required_columns[0]])
    return ""


def _infer_resource_type(control_ref: str) -> str:
    ref = control_ref.lower()
    if "s3" in ref or "bucket" in ref:
        return "s3_bucket"
    if "rds" in ref or "db_instance" in ref:
        return "rds_instance"
    if "iam" in ref or "user" in ref or "root" in ref:
        return "iam_user"
    if "nacl" in ref or "network_acl" in ref:
        return "network_acl"
    if "security_hub" in ref or "hub" in ref:
        return "security_hub"
    if "config" in ref:
        return "aws_config"
    return "resource"
