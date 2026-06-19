"""Canonical JSON hashing for determinism and auditability."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def canonical_dumps(obj: Any) -> str:
    """Serialize to canonical JSON: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def canonical_hash(obj: dict[str, Any] | list[Any]) -> str:
    """SHA256 of canonical JSON. Same input -> same hash."""
    normalized = canonical_dumps(obj)
    return hashlib.sha256(normalized.encode()).hexdigest()


def record_hash(row: dict[str, Any]) -> str:
    """Hash for a single snapshot row (payload)."""
    return canonical_hash(row)


def snapshot_hash_from_record_hashes(record_hashes: list[str]) -> str:
    """Deterministic snapshot hash from ordered list of record_hashes."""
    return canonical_hash(record_hashes)


def rule_definition_hash(rule: dict[str, Any]) -> str:
    """Hash for a rule definition (control_ref, pass_rule, required_columns, etc.)."""
    return canonical_hash(rule)


def result_hash(payload: dict[str, Any]) -> str:
    """Hash for a control result payload (for chaining)."""
    return canonical_hash(payload)
