import os
import sys

import pytest

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use local storage and test DB in tests
os.environ.setdefault("USE_LOCAL_STORAGE", "true")
os.environ.setdefault("LOCAL_STORAGE_PATH", "/tmp/steampipe_test_snapshots")


@pytest.fixture
def tmp_storage_path(tmp_path):
    return tmp_path / "snapshots"
