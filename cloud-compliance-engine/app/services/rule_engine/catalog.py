"""Framework catalog paths and rule extraction from the single source of truth."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.hash_utils import rule_definition_hash

# Repo root: steampipe/ (parent of cloud-compliance-engine/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_QUERIES_PATH = REPO_ROOT / "data" / "queries.json"
CONTROLS_YAML_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "cis_v6_controls.yaml"

CIS_AWS_V6_FRAMEWORK_ID = "cis_aws_v6"
DEFAULT_FRAMEWORK_VERSION = "6.0.0"


def rule_def_for_hash(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "control_id": meta.get("control_id"),
        "control_ref": meta.get("control_ref"),
        "pass_rule": meta.get("pass_rule") or "zero_rows",
        "required_columns": sorted(meta.get("required_columns") or []),
    }


def rule_from_query_entry(entry: dict[str, Any], framework_id: str = CIS_AWS_V6_FRAMEWORK_ID) -> dict[str, Any] | None:
    """Build an evaluation rule from one data/queries.json entry."""
    meta = entry.get("extra_metadata") or {}
    if meta.get("category") != "compliance":
        return None
    if meta.get("framework_id", framework_id) != framework_id:
        return None
    control_ref = meta.get("control_ref")
    if not control_ref:
        return None
    rule_def = rule_def_for_hash(meta)
    return {
        "name": entry.get("name"),
        "query_id": entry.get("id"),
        "framework_id": framework_id,
        "control_id": meta.get("control_id") or control_ref,
        "control_ref": control_ref,
        "pass_rule": meta.get("pass_rule") or "zero_rows",
        "required_columns": meta.get("required_columns") or [],
        "rule_definition_hash": rule_definition_hash(rule_def),
    }


def load_compliance_rules_from_data_queries(
    path: Path | None = None,
    framework_id: str = CIS_AWS_V6_FRAMEWORK_ID,
) -> list[dict[str, Any]]:
    """Load evaluation rules from data/queries.json (single source of truth)."""
    path = path or DATA_QUERIES_PATH
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rules: list[dict[str, Any]] = []
    for entry in data.get("queries") or []:
        rule = rule_from_query_entry(entry, framework_id)
        if rule:
            rules.append(rule)
    return rules


def load_compliance_rules_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Build rule from Bronze snapshot metadata (runtime fallback)."""
    control_ref = metadata.get("control_ref")
    if not control_ref:
        return None
    rule_def = rule_def_for_hash(metadata)
    return {
        "control_id": metadata.get("control_id") or control_ref,
        "control_ref": control_ref,
        "pass_rule": metadata.get("pass_rule") or "zero_rows",
        "required_columns": metadata.get("required_columns") or [],
        "rule_definition_hash": metadata.get("rule_definition_hash") or rule_definition_hash(rule_def),
        "framework_id": metadata.get("framework_id") or CIS_AWS_V6_FRAMEWORK_ID,
    }


def build_pinned_rule_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Freeze scan-time rule fields from Bronze metadata for Silver snapshot row."""
    rule_def = rule_def_for_hash(meta)
    return {
        "control_ref": meta.get("control_ref"),
        "control_id": meta.get("control_id"),
        "framework_id": meta.get("framework_id"),
        "pass_rule": meta.get("pass_rule") or "zero_rows",
        "required_columns": list(meta.get("required_columns") or []),
        "natural_key": meta.get("natural_key"),
        "rule_definition_hash": rule_definition_hash(rule_def),
        "schema_version": meta.get("schema_version"),
        "pinned_at": "extract",
    }
