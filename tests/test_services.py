import pytest
from pathlib import Path

from src.services.snapshot import SnapshotService


def test_snapshot_persist(tmp_path):
    service = SnapshotService(use_local_storage=True, local_storage_path=tmp_path)
    path = service.persist_snapshot(
        tenant_id="t1",
        execution_id="e1",
        query_id="q1",
        account_id="a1",
        provider="aws",
        account_identifier="123456789",
        region="us-east-1",
        data={"rows": [{"id": 1}]},
    )
    assert path
    full = Path(path)
    assert full.exists()
    assert "result.json" in str(full)
    content = full.read_text()
    assert "rows" in content
