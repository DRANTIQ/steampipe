import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
# DATABASE_URL must point to a real Postgres for API tests (see user_input.md or use test DB)

from src.app import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_live():
    response = client.get("/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "execution_total" in response.text or "queue_depth" in response.text
