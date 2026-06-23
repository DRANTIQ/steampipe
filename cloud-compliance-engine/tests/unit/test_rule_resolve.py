"""Tests for rule resolution: bronze pinning vs catalog."""
from __future__ import annotations

from uuid import uuid4

from app.models.compliance import RuleVersion, Snapshot
from app.services.rule_engine.catalog import build_pinned_rule_metadata
from app.services.rule_engine.registry import RuleRegistry
from app.services.rule_engine.resolve import (
    get_rule_from_version_definitions,
    resolve_evaluation_rule,
)


def test_build_pinned_rule_metadata_includes_hash():
    meta = {
        "control_ref": "security-hub-enabled",
        "control_id": "3.1.1",
        "framework_id": "cis_aws_v6",
        "pass_rule": "zero_rows",
        "required_columns": ["account_id", "region"],
    }
    pinned = build_pinned_rule_metadata(meta)
    assert pinned["control_ref"] == "security-hub-enabled"
    assert pinned["pass_rule"] == "zero_rows"
    assert pinned["rule_definition_hash"]
    assert pinned["pinned_at"] == "extract"


def test_get_rule_from_version_definitions():
    rv = RuleVersion(
        id=uuid4(),
        framework_id="cis_aws_v6",
        version_name="6.0.0",
        hash="abc",
        definitions=[
            {
                "control_ref": "iam-root-mfa",
                "pass_rule": "zero_rows",
                "required_columns": ["user_name"],
                "rule_definition_hash": "hash123",
            }
        ],
    )
    rule = get_rule_from_version_definitions(rv, "iam-root-mfa")
    assert rule is not None
    assert rule["pass_rule"] == "zero_rows"
    assert get_rule_from_version_definitions(rv, "missing") is None


def test_resolve_prefers_bronze_over_live_catalog():
    """Job-linked snapshot with pinned metadata must not use live catalog pass_rule."""
    registry = RuleRegistry()
    registry.register(
        {
            "control_ref": "test-control",
            "control_id": "1.0",
            "pass_rule": "zero_rows",
            "required_columns": [],
            "rule_definition_hash": "live-hash",
        }
    )

    snapshot = Snapshot(
        id=uuid4(),
        tenant_id=uuid4(),
        account_id=uuid4(),
        snapshot_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        snapshot_hash="snap-hash",
        record_count=0,
        execution_job_id=str(uuid4()),
        framework_id="cis_aws_v6",
        control_ref="test-control",
        rule_metadata=build_pinned_rule_metadata(
            {
                "control_ref": "test-control",
                "control_id": "1.0",
                "framework_id": "cis_aws_v6",
                "pass_rule": "zero_rows",
                "required_columns": ["arn"],
            }
        ),
    )

    class FakeSession:
        def execute(self, *_args, **_kwargs):
            class Result:
                def scalars(self):
                    return self

                def first(self):
                    return None

            return Result()

        def flush(self):
            pass

    resolved = resolve_evaluation_rule(FakeSession(), snapshot, "test-control", "cis_aws_v6", registry)
    assert resolved is not None
    assert resolved.rule_source == "bronze"
    assert resolved.rule["required_columns"] == ["arn"]
    assert resolved.rule["rule_definition_hash"] != "live-hash"
