"""Unit tests for JWT auth (T-022)."""
from src.services.auth import create_access_token, decode_access_token


def test_jwt_roundtrip():
    token = create_access_token(
        user_id="u1",
        tenant_id="5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47",
        role="tenant_admin",
        email="test@example.com",
        expires_minutes=60,
    )
    payload = decode_access_token(token)
    assert payload.user_id == "u1"
    assert payload.tenant_id == "5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47"
    assert payload.role == "tenant_admin"
    assert payload.email == "test@example.com"
