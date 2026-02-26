# 🧪 Local Testing & Unit Tests

## 1️⃣ Prerequisites

Before testing locally, make sure:

- **Remote PostgreSQL, Redis, and S3** are available. Use the connection strings and env vars from **user_input.md** in your `.env`.
- **Steampipe** is installed locally (`steampipe --version`).
- **Required plugins** are installed:

  ```bash
  steampipe plugin install aws azure gcp kubernetes github gitlab terraform
  ```

- **`.env`** is configured from **user_input.md** (remote DB, Redis, S3; JWT and feature flags).
- **Python dependencies** are installed:

  ```bash
  python3.11 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

## 2️⃣ Run Local Services

For testing, you need **3 processes**:

### API

```bash
./scripts/run_api.sh
```

- Serves FastAPI endpoints: `/docs`, `/health`, `/ready`, `/live`.
- API requests are validated against DB and Redis.
- No Steampipe execution occurs in API.

### Worker

```bash
./scripts/run_worker.sh
```

- Polls job queue (Redis/SQS) for execution jobs.
- Executes Steampipe queries.
- Saves snapshots to S3 or local path.
- Updates job status in DB.

### Scheduler

```bash
./scripts/run_scheduler.sh
```

- Polls `QuerySchedule` table for pending cron jobs.
- Creates `ExecutionJob` entries in Redis queue.
- Does not execute Steampipe directly.

## 3️⃣ Basic Unit & Integration Tests

### Using pytest

Install pytest:

```bash
pip install pytest pytest-asyncio
```

**Test folder structure:**

```
tests/
├── test_api.py
├── test_services.py
├── test_worker.py
└── conftest.py  # fixtures: test DB session, Redis mock, S3 mock
```

### 3a. API Tests

Use `httpx` or FastAPI `TestClient` to test endpoints.

```python
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

### 3b. Service Tests

Mock S3, Steampipe, and SecretsManager to test services in isolation.

```python
def test_snapshot_persist(tmp_path):
    from src.services.snapshot import SnapshotService
    snapshot_service = SnapshotService(
        use_local_storage=True,
        local_storage_path=tmp_path
    )
    data = {"test": 123}
    path = snapshot_service.persist_snapshot("tenant_id", "exec_id", "query_id", 1, "aws", "account_id", "us-east-1", data)
    assert path.exists()
```

### 3c. Worker Tests

- Use a fake queue or Redis mock to push a job.
- Ensure `ExecutionWorker.execute()` updates job status and stores snapshot.

## 4️⃣ Local Dry-Run (Optional)

You can create a fake `CloudAccount` with test credentials and run a single query without hitting real AWS/GCP:

```http
POST /executions
{
    "tenant_id": "...",
    "account_id": "...",
    "query_id": "sample-aws-query"
}
```

Worker will process and write snapshot to S3 (or set `USE_LOCAL_STORAGE=true` only for local dev/testing).

---

✅ **Adding this section in your documentation ensures:**

- Developers can validate setup locally
- Basic unit & integration test coverage exists
