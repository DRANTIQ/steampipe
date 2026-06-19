"""Load control and rule definitions from config; compute rule_definition_hash."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from app.services.hash_utils import rule_definition_hash

# Framework id used in DB and API
CIS_AWS_V6_FRAMEWORK_ID = "cis_aws_v6"
DEFAULT_FRAMEWORK_VERSION = "6.0.0"


def _rule_def_for_hash(q: dict[str, Any]) -> dict[str, Any]:
    """Stable subset of query for rule_definition_hash."""
    return {
        "control_id": q.get("control_id"),
        "control_ref": q.get("control_ref"),
        "pass_rule": q.get("pass_rule"),
        "required_columns": sorted(q.get("required_columns") or []),
    }


def load_controls_from_yaml(path: str | Path) -> tuple[str, str, list[dict[str, Any]]]:
    """Load config/cis_v6_controls.yaml. Returns (framework_name, framework_version, controls_list)."""
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}
    framework = data.get("framework", "CIS AWS Foundations Benchmark v6.0.0")
    version = data.get("framework_version", "6.0.0")
    controls = data.get("controls") or []
    return framework, version, controls


def load_rules_from_queries_json(path: str | Path) -> tuple[str, list[dict[str, Any]]]:
    """Load queries/cis_v6_queries.json. Returns (framework_name, list of rule dicts with rule_definition_hash)."""
    path = Path(path)
    data = json.loads(path.read_text())
    framework = data.get("framework", "CIS AWS Foundations Benchmark v6.0.0")
    queries = data.get("queries") or []
    rules = []
    for q in queries:
        rule_def = _rule_def_for_hash(q)
        rules.append({
            "name": q.get("name"),
            "control_id": q.get("control_id"),
            "control_ref": q.get("control_ref"),
            "pass_rule": q.get("pass_rule"),
            "required_columns": q.get("required_columns") or [],
            "rule_definition_hash": rule_definition_hash(rule_def),
        })
    return framework, rules


class RuleRegistry:
    """In-memory registry of rules by control_ref for evaluation."""

    def __init__(self) -> None:
        self._by_control_ref: dict[str, dict[str, Any]] = {}

    def register(self, rule: dict[str, Any]) -> None:
        ref = rule.get("control_ref")
        if ref:
            self._by_control_ref[ref] = rule

    def load_from_queries_json(self, path: str | Path) -> str:
        """Load rules from JSON; return framework name."""
        framework, rules = load_rules_from_queries_json(path)
        for r in rules:
            self.register(r)
        return framework

    def get(self, control_ref: str) -> dict[str, Any] | None:
        return self._by_control_ref.get(control_ref)

    def all_control_refs(self) -> list[str]:
        return list(self._by_control_ref.keys())
