"""Tests for query catalog filtering."""
from types import SimpleNamespace

from src.services.query_catalog import filter_queries, query_matches_framework


def _query(provider: str, meta: dict | None, active: bool = True):
    return SimpleNamespace(provider=provider, extra_metadata=meta, active=active)


def test_query_matches_framework_by_title():
    meta = {"framework": "CIS AWS Foundations Benchmark v6.0.0", "category": "compliance"}
    assert query_matches_framework(meta, "cis_aws_v6")


def test_filter_compliance_aws():
    queries = [
        _query("aws", {"category": "inventory"}),
        _query("aws", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "x"}),
        _query("azure", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "x"}),
    ]
    matched = filter_queries(queries, provider="aws", category="compliance", framework_id="cis_aws_v6", exclude_legacy=True)
    assert len(matched) == 1


def test_filter_excludes_legacy():
    queries = [
        _query("aws", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "a", "legacy": True}),
        _query("aws", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "b"}),
    ]
    matched = filter_queries(queries, provider="aws", category="compliance", framework_id="cis_aws_v6", exclude_legacy=True)
    assert len(matched) == 1
    assert matched[0].extra_metadata["control_ref"] == "b"


def test_filter_requires_control_ref_for_compliance():
    queries = [
        _query("aws", {"category": "compliance", "framework_id": "cis_aws_v6"}),
        _query("aws", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "ok"}),
    ]
    matched = filter_queries(queries, provider="aws", category="compliance", framework_id="cis_aws_v6")
    assert len(matched) == 1


def test_filter_inactive_excluded():
    queries = [
        _query("aws", {"category": "compliance", "framework": "CIS AWS Foundations Benchmark v6.0.0"}, active=False),
    ]
    matched = filter_queries(queries, provider="aws", category="compliance", framework_id="cis_aws_v6")
    assert matched == []
