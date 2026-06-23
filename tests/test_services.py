import pytest
from pathlib import Path

from src.services.snapshot import SnapshotService
from src.services.snapshot_document import build_snapshot_document


def test_snapshot_persist(tmp_path):
    service = SnapshotService(use_local_storage=True, local_storage_path=tmp_path)
    payload = build_snapshot_document(
        steampipe_output={"rows": [{"id": 1}]},
        execution_job_id="e1",
        query_id="q1",
        query_name="test_query",
        tenant_id="t1",
        account_id="a1",
        provider="aws",
        extra_metadata={"category": "compliance", "framework_id": "cis_aws_v6"},
    )
    path = service.persist_snapshot(
        tenant_id="t1",
        tenant_name="Acme Corp",
        execution_id="e1",
        query_id="q1",
        account_id="a1",
        provider="aws",
        account_identifier="387957186076",
        region="us-east-1",
        data=payload,
    )
    assert path
    full = Path(path)
    assert full.exists()
    normalized = str(full).replace("\\", "/")
    assert "acme-corp/aws/387957186076" in normalized
    assert "result.json" in normalized
    content = full.read_text()
    assert "metadata" in content
    assert "rows" in content
    assert "execution_job_id" in content


def test_snapshot_persist_with_batch_id(tmp_path):
    service = SnapshotService(use_local_storage=True, local_storage_path=tmp_path)
    payload = build_snapshot_document(
        steampipe_output={"rows": []},
        execution_job_id="job-1",
        query_id="q1",
        query_name="test_query",
        tenant_id="t1",
        account_id="a1",
        provider="aws",
        batch_id="batch-abc",
    )
    path = service.persist_snapshot(
        tenant_id="t1",
        tenant_name="Acme Corp",
        execution_id="job-1",
        query_id="q1",
        account_id="a1",
        provider="aws",
        account_identifier="387957186076",
        region="us-east-1",
        data=payload,
        batch_id="batch-abc",
    )
    normalized = str(path).replace("\\", "/")
    assert "/batch-abc/job-1/result.json" in normalized
