"""Backward-compatible re-export. Rules load from data/queries.json or public.queries."""
from app.services.rule_engine.registry import (
    CIS_AWS_V6_FRAMEWORK_ID,
    DATA_QUERIES_PATH,
    DEFAULT_FRAMEWORK_VERSION,
    RuleRegistry,
    get_default_registry,
    get_registry,
    load_controls_from_yaml,
    load_rules_from_data_queries,
)

# Legacy name used by seed_catalog
load_rules_from_queries_json = load_rules_from_data_queries

__all__ = [
    "CIS_AWS_V6_FRAMEWORK_ID",
    "DATA_QUERIES_PATH",
    "DEFAULT_FRAMEWORK_VERSION",
    "RuleRegistry",
    "get_default_registry",
    "get_registry",
    "load_controls_from_yaml",
    "load_rules_from_data_queries",
    "load_rules_from_queries_json",
]
