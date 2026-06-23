"""Tests for job_completed Redis payload builder."""
from src.services.job_completed_event import build_job_completed_payload


def test_build_job_completed_payload_includes_pass_rule_and_columns():
    payload = build_job_completed_payload(
        job_id="job-1",
        snapshot_path="local/snapshots/t/a/result.json",
        tenant_id="tenant-1",
        account_id="account-1",
        query_id="query-1",
        batch_id="batch-1",
        extra_metadata={
            "control_ref": "iam-root-mfa",
            "framework_id": "cis_aws_v6",
            "category": "compliance",
            "pass_rule": "zero_rows",
            "required_columns": ["user_name", "mfa_active"],
            "natural_key": "user_name",
        },
        row_count=0,
    )
    assert payload["pass_rule"] == "zero_rows"
    assert payload["required_columns"] == ["user_name", "mfa_active"]
    assert payload["natural_key"] == "user_name"
    assert payload["control_ref"] == "iam-root-mfa"


def test_build_job_completed_payload_omits_empty_optional_fields():
    payload = build_job_completed_payload(
        job_id="job-1",
        snapshot_path=None,
        tenant_id="t",
        account_id="a",
        query_id="q",
        batch_id=None,
        extra_metadata={"control_ref": "x"},
        row_count=1,
    )
    assert "pass_rule" not in payload
    assert "required_columns" not in payload
