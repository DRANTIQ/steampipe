"""Tests for compliance rule loading from data/queries.json."""
from pathlib import Path

from app.services.rule_engine.catalog import DATA_QUERIES_PATH, load_compliance_rules_from_data_queries
from app.services.rule_engine.registry import RuleRegistry


def test_data_queries_path_exists():
    assert DATA_QUERIES_PATH.exists(), f"Missing catalog: {DATA_QUERIES_PATH}"


def test_load_compliance_rules_from_data_queries():
    rules = load_compliance_rules_from_data_queries()
    assert len(rules) >= 30
    refs = {r["control_ref"] for r in rules}
    assert "security-hub-enabled" in refs or "iam-root-mfa" in refs
    for rule in rules:
        assert rule.get("pass_rule") == "zero_rows"
        assert rule.get("control_ref")
        assert rule.get("rule_definition_hash")


def test_registry_load_from_data_queries():
    registry = RuleRegistry()
    count = registry.load_from_data_queries(DATA_QUERIES_PATH)
    assert count >= 30
    assert registry.get(registry.all_control_refs()[0]) is not None
