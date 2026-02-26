# Cloud Governance & Cost Intelligence Platform

Multi-tenant platform for running **Steampipe** SQL and benchmark queries across AWS, Azure, GCP, Kubernetes, GitHub, GitLab, and Terraform. Async job queue (Redis), snapshot storage (S3), REST API (FastAPI).

## Quick start (local)

1. **Copy env**  
   Create `.env` from `user_input.md` (see also `env.example`). Set `DATABASE_URL`, `REDIS_URL`, S3 or `USE_LOCAL_STORAGE=true` and `LOCAL_STORAGE_PATH=./local/snapshots`.

2. **Python**  
   `python3.11 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`

3. **Steampipe** (for worker)  
   Install [Steampipe](https://steampipe.io/docs/install) and plugins, e.g.:  
   `steampipe plugin install aws azure gcp kubernetes github gitlab terraform`

4. **DB**  
   `./scripts/init_db.sh`  
   Optional: `python scripts/seed_dummy_data.py`

5. **Run** (three processes)  
   - API: `./scripts/run_api.sh` → http://localhost:8000 (e.g. `/docs`, `/health`)  
   - Worker: `./scripts/run_worker.sh`  
   - Scheduler: `./scripts/run_scheduler.sh`

## Project layout

- `src/app.py` – FastAPI app (`/health`, `/ready`, `/live`, `/metrics`, `/api/v1/...`)
- `src/config/` – Settings from env
- `src/models/` – SQLAlchemy models
- `src/services/` – DB, queue (Redis), snapshot (S3/local), secrets
- `src/api/` – Routes: tenants, accounts, queries, schedules, executions
- `src/workers/` – Execution worker (runs Steampipe)
- `src/scheduler/` – Cron scheduler (enqueues jobs)
- `alembic/` – Migrations
- `scripts/` – init_db, seed, run_api, run_worker, run_scheduler

## API (base `/api/v1`)

| Resource   | Methods |
|-----------|---------|
| Tenants   | POST, GET, GET /{id} |
| Accounts  | POST /tenants/{id}/accounts, GET /tenants/{id}/accounts |
| Queries   | POST, GET |
| Schedules | POST, GET |
| Executions | POST, GET, GET /{job_id}, GET /{job_id}/result |

**POST /executions** – Enqueue a run (returns `job_id`). Worker executes Steampipe and stores the snapshot.

## Docs

- **LOCAL_DEVELOPMENT.md** – Migrations, dummy data, local run
- **Testing.md** – Running services and pytest
- **user_input.md** – Canonical `.env` values (Postgres, Redis, S3)

## Docker (Linux; recommended to avoid macOS cert/keychain issues)

All three processes (API, worker, scheduler) run in containers with `.env` loaded via `env_file`. Postgres and Redis must be reachable (e.g. from `.env`).

```bash
# Create .env from env.example / user_input.md (DATABASE_URL, REDIS_URL, S3 or USE_LOCAL_STORAGE, etc.)
docker compose build
docker compose up
# API: http://localhost:8000
```

- **api** – uvicorn on port 8000  
- **worker** – runs Steampipe (uses `/app/steampipe/worker_install` with AWS plugin; no macOS keychain). For AWS queries the worker needs **master account** credentials in `.env`: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_SESSION_TOKEN` (for temporary creds). With assume-role, the worker uses these to assume the child role per job. Or use an IAM role when the worker runs on AWS.  
- **scheduler** – enqueues jobs from schedules  

Single service with env file:  
`docker run -p 8000:8000 --env-file .env steampipe-platform`
