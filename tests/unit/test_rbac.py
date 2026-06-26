"""Unit tests for tenant RBAC helpers."""
from src.api.deps import (
    can_manage_tenant,
    can_run_scans,
    is_viewer,
)
from src.services.auth import TokenPayload


def _payload(role: str) -> TokenPayload:
    return TokenPayload(user_id="u1", tenant_id="t1", role=role, email="a@b.c")


def test_viewer_is_read_only():
    auth = _payload("viewer")
    assert is_viewer(auth) is True
    assert can_run_scans(auth) is False
    assert can_manage_tenant(auth) is False


def test_tenant_user_can_run_scans():
    auth = _payload("tenant_user")
    assert can_run_scans(auth) is True
    assert can_manage_tenant(auth) is False


def test_tenant_admin_full_tenant_ops():
    auth = _payload("tenant_admin")
    assert can_run_scans(auth) is True
    assert can_manage_tenant(auth) is True
