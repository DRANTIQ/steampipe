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

**Canonical documentation:** [infra-state-docs](../infra-state-docs/README.md) (sibling repo).

| Topic | Location |
|-------|----------|
| Task tracker | `infra-state-docs/platform/TASK_TRACKER.md` |
| Stage 1 full guide | `infra-state-docs/steampipe/STAGE1_FULL_GUIDE.md` |
| CIS scan | `infra-state-docs/steampipe/CIS_SCAN_RUNBOOK.md` |
| Remote DB | `infra-state-docs/steampipe/RUN_WITH_REMOTE_DB.md` |
| Compliance platform | `infra-state-docs/platform/COMPLIANCE_PLATFORM.md` |
| Local dev | `LOCAL_DEVELOPMENT.md` (this repo) |

Stage 2 compliance runs from **cloud-compliance-engine** repo (`docker compose up` on port 8001).

## Docker (Linux; recommended to avoid macOS cert/keychain issues)

**Local Postgres + Redis (all-in-one):**

```bash
docker compose build
docker compose up
# API: http://localhost:8000
```

**Remote Postgres + Redis (Supabase, Upstash from `.env`) — no local DB containers:**

```bash
docker compose -f docker-compose.remote.yml build
docker compose -f docker-compose.remote.yml up
```

See **docs/RUN_WITH_REMOTE_DB.md** for init migrations and `.env` setup.

- **api** – uvicorn on port 8000  
- **worker** – runs Steampipe (uses `/app/steampipe/worker_install` with AWS plugin; no macOS keychain). For AWS queries the worker needs **master account** credentials in `.env`: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_SESSION_TOKEN` (for temporary creds). With assume-role, the worker uses these to assume the child role per job. Or use an IAM role when the worker runs on AWS.  
- **scheduler** – enqueues jobs from schedules  

Single service with env file:  
`docker run -p 8000:8000 --env-file .env steampipe-platform`
