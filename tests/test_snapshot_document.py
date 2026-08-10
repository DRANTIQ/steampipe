"""Tests for snapshot document builder."""
from src.services.snapshot_document import build_snapshot_document, infer_natural_key, normalize_steampipe_output


def test_infer_natural_key_prefers_name():
    assert infer_natural_key(["region", "name", "account_id"]) == "name"


def test_normalize_list_output():
    rows, cols = normalize_steampipe_output([{"a": 1}])
    assert rows == [{"a": 1}]
    assert cols is None


def test_build_snapshot_document_wraps_metadata():
    doc = build_snapshot_document(
        steampipe_output={"columns": [{"name": "x"}], "rows": []},
        execution_job_id="job-1",
        query_id="q-1",
        query_name="cis_2_3_iam_root_access_keys",
        tenant_id="t-1",
        account_id="a-1",
        provider="aws",
        batch_id="batch-1",
        extra_metadata={
            "category": "compliance",
            "framework_id": "cis_aws_v6",
            "control_ref": "iam-root-access-keys",
            "control_id": "2.3",
            "pass_rule": "zero_rows",
            "required_columns": ["account_id"],
        },
    )
    assert doc["metadata"]["execution_job_id"] == "job-1"
    assert doc["metadata"]["control_ref"] == "iam-root-access-keys"
    assert doc["metadata"]["framework_id"] == "cis_aws_v6"
    assert doc["metadata"]["natural_key"] == "account_id"
    assert doc["metadata"]["schema_version"] == "1.0"
    assert doc["rows"] == []
    assert "columns" in doc
