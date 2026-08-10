"""Tests for scheduled framework scan helpers."""
from src.services.query_catalog import filter_queries


def _query(provider: str, meta: dict):
    return SimpleNamespace(provider=provider, extra_metadata=meta, deleted_at=None, active=True)


class SimpleNamespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_filter_queries_for_cis_scan():
    queries = [
        _query("aws", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "a"}),
        _query("aws", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "b", "legacy": True}),
        _query("aws", {"category": "cost", "framework_id": "cis_aws_v6"}),
        _query("azure", {"category": "compliance", "framework_id": "cis_aws_v6", "control_ref": "c"}),
    ]
    matched = filter_queries(
        queries,
        provider="aws",
        category="compliance",
        framework_id="cis_aws_v6",
        exclude_legacy=True,
    )
    assert len(matched) == 1
    assert matched[0].extra_metadata["control_ref"] == "a"
