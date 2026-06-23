"""Load and resolve evaluation rules from data/queries.json or public.queries."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.hash_utils import rule_definition_hash
from app.services.rule_engine.catalog import (
    CIS_AWS_V6_FRAMEWORK_ID,
    DATA_QUERIES_PATH,
    DEFAULT_FRAMEWORK_VERSION,
    load_compliance_rules_from_data_queries,
    rule_def_for_hash,
)

__all__ = [
    "CIS_AWS_V6_FRAMEWORK_ID",
    "DATA_QUERIES_PATH",
    "DEFAULT_FRAMEWORK_VERSION",
    "RuleRegistry",
    "get_registry",
    "get_default_registry",
    "load_controls_from_yaml",
    "load_rules_from_data_queries",
]


def load_controls_from_yaml(path: str | Path) -> tuple[str, str, list[dict[str, Any]]]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    framework = data.get("framework", "CIS AWS Foundations Benchmark v6.0.0")
    version = data.get("framework_version", DEFAULT_FRAMEWORK_VERSION)
    controls = data.get("controls") or []
    return framework, version, controls


def load_rules_from_data_queries(path: str | Path | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Return (framework_label, rules) from data/queries.json."""
    path = Path(path) if path else DATA_QUERIES_PATH
    rules = load_compliance_rules_from_data_queries(path)
    return "CIS AWS Foundations Benchmark v6.0.0", rules


class RuleRegistry:
    """In-memory evaluation rules keyed by control_ref."""

    def __init__(self) -> None:
        self._by_control_ref: dict[str, dict[str, Any]] = {}
        self._framework_id: str = CIS_AWS_V6_FRAMEWORK_ID

    def register(self, rule: dict[str, Any]) -> None:
        ref = rule.get("control_ref")
        if ref:
            self._by_control_ref[ref] = rule

    def load_from_data_queries(
        self,
        path: str | Path | None = None,
        framework_id: str = CIS_AWS_V6_FRAMEWORK_ID,
    ) -> int:
        self._framework_id = framework_id
        rules = load_compliance_rules_from_data_queries(Path(path) if path else DATA_QUERIES_PATH, framework_id)
        for rule in rules:
            self.register(rule)
        return len(self._by_control_ref)

    def load_from_database(self, db: Session, framework_id: str = CIS_AWS_V6_FRAMEWORK_ID) -> int:
        """Load rules from public.queries.extra_metadata (same source Stage 1 executes)."""
        self._framework_id = framework_id
        rows = db.execute(
            text("""
                SELECT id, name, extra_metadata
                FROM queries
                WHERE active = true AND deleted_at IS NULL
            """)
        ).mappings().all()
        count = 0
        for row in rows:
            meta = row["extra_metadata"] or {}
            if isinstance(meta, str):
                meta = json.loads(meta)
            if meta.get("category") != "compliance":
                continue
            if meta.get("framework_id", framework_id) != framework_id:
                continue
            control_ref = meta.get("control_ref")
            if not control_ref:
                continue
            rule_def = rule_def_for_hash(meta)
            self.register(
                {
                    "name": row["name"],
                    "query_id": str(row["id"]),
                    "framework_id": framework_id,
                    "control_id": meta.get("control_id") or control_ref,
                    "control_ref": control_ref,
                    "pass_rule": meta.get("pass_rule") or "zero_rows",
                    "required_columns": meta.get("required_columns") or [],
                    "rule_definition_hash": rule_definition_hash(rule_def),
                }
            )
            count += 1
        return count

    def get(self, control_ref: str) -> dict[str, Any] | None:
        return self._by_control_ref.get(control_ref)

    def register_ephemeral(self, rule: dict[str, Any]) -> None:
        """Register a one-off rule (e.g. from snapshot metadata)."""
        self.register(rule)

    def all_control_refs(self) -> list[str]:
        return list(self._by_control_ref.keys())

    @property
    def framework_id(self) -> str:
        return self._framework_id

    def automated_control_count(self) -> int:
        return len(self._by_control_ref)


def get_registry(db: Session | None = None, framework_id: str = CIS_AWS_V6_FRAMEWORK_ID) -> RuleRegistry:
    """Prefer DB (Stage 1 queries table), fall back to data/queries.json file."""
    registry = RuleRegistry()
    if db is not None:
        if registry.load_from_database(db, framework_id) > 0:
            return registry
    if DATA_QUERIES_PATH.exists():
        registry.load_from_data_queries(DATA_QUERIES_PATH, framework_id)
    return registry


def get_default_registry() -> RuleRegistry:
    return get_registry(None)
