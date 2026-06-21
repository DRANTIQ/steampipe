# Stage 1 — Full Guide

Complete reference for the **Steampipe Execution Platform** (Stage 1): file structure, architecture, all APIs, data flow, and how to run it.

Stage 2 (`cloud-compliance-engine/`) is mentioned briefly at the end for context. This doc focuses on Stage 1 only.

---

## Table of contents

1. [What Stage 1 does](#1-what-stage-1-does)
2. [Repo layout](#2-repo-layout)
3. [How the layers connect](#3-how-the-layers-connect)
4. [Database tables](#4-database-tables)
5. [All APIs](#5-all-apis)
6. [End-to-end: one query run](#6-end-to-end-one-query-run)
7. [Key services](#7-key-services)
8. [Scripts reference](#8-scripts-reference)
9. [Configuration (.env)](#9-configuration-env)
10. [How to run](#10-how-to-run) — see also [RUN_WITH_REMOTE_DB.md](RUN_WITH_REMOTE_DB.md) for Supabase + Upstash
11. [Stage 2 (brief)](#11-stage-2-brief)
12. [Quick reference](#12-quick-reference)

---

## 1. What Stage 1 does

**Goal:** Run Steampipe SQL against cloud accounts, store JSON snapshots, track jobs in Postgres.

**Three separate processes** (never combined into one):

| Process    | Role                                      | Runs Steampipe? |
|------------|-------------------------------------------|-----------------|
| **API**    | Accepts requests, writes jobs to Redis    | **Never**       |
| **Worker** | Pulls jobs, runs Steampipe, saves snapshots | **Yes — only this one** |
| **Scheduler** | Cron → creates jobs on a timer         | **Never**       |

**Rule:** Only the **worker** runs Steampipe. API and scheduler never do.

**Output:** JSON snapshot files (local or S3) + metadata in Postgres (`execution_jobs`, `execution_results`).

---

## 2. Repo layout

```
steampipe/
│
├── .env                          # Config (Postgres, Redis, AWS, S3/local snapshots)
├── docker-compose.yml            # Full stack: postgres, redis, api, worker, scheduler
├── docker-compose.local.yml      # Just postgres + redis (run app processes locally)
├── Dockerfile                    # Python 3.11 + Steampipe (for worker in Docker)
├── requirements.txt
├── alembic.ini + alembic/        # DB migrations
│
├── data/
│   └── queries.json              # 49 Steampipe queries (CIS + inventory)
│
├── scripts/
│   ├── init_db.sh                # alembic upgrade head
│   ├── seed_dummy_data.py        # tenants, accounts, sample queries
│   ├── apply_queries_document.py # load data/queries.json → DB
│   ├── run_api.sh                # start FastAPI
│   ├── run_worker.sh             # start worker loop
│   ├── run_scheduler.sh          # start cron scheduler
│   └── check_aws_connectivity.py # debug AWS creds
│
└── src/                          ← STAGE 1 CODE
    ├── app.py                    # FastAPI entry (/health, /docs, /metrics)
    ├── config/
    │   └── settings.py           # reads .env (DATABASE_URL, REDIS_URL, S3, AWS...)
    │
    ├── api/
    │   ├── deps.py               # DB session injection
    │   ├── schemas.py            # Pydantic request/response models
    │   └── routes/
    │       ├── tenants.py
    │       ├── accounts.py
    │       ├── queries.py
    │       ├── schedules.py
    │       └── executions.py     # main execution flow
    │
    ├── models/                   # SQLAlchemy → Postgres tables
    │   ├── tenant.py
    │   ├── cloud_account.py
    │   ├── query.py
    │   ├── query_schedule.py
    │   ├── execution_job.py
    │   ├── execution_result.py
    │   ├── execution_batch.py
    │   ├── user.py
    │   ├── api_key.py
    │   └── enums.py              # aws, queued, success, etc.
    │
    ├── services/
    │   ├── database.py           # SQLAlchemy engine + sessions
    │   ├── queue.py              # Redis push/pop (steampipe:execution_jobs)
    │   ├── snapshot.py           # write/read JSON (local or S3)
    │   ├── secrets.py            # resolve account credentials
    │   └── query_hash.py         # SHA-256 of query text
    │
    ├── workers/
    │   └── execution_worker.py   # THE Steampipe runner
    │
    └── scheduler/
        └── cron_scheduler.py     # cron → create jobs
```

---

## 3. How the layers connect

```
You / Frontend / curl
        │
        ▼
┌───────────────────────────────────────┐
│  API  (src/app.py + src/api/routes/*) │
│  REST /api/v1/...                     │
└───────────┬───────────────────────────┘
            │
     ┌──────┴──────┐
     ▼             ▼
 Postgres       Redis
 (metadata)     (job queue)
     ▲             │
     │             ▼
     │        Worker + Steampipe
     │             │
     └─────────────┴──► Snapshots (local or S3)

Scheduler ──► Postgres + Redis  (creates jobs on cron; no Steampipe)
```

| Layer      | File(s)                    | Responsibility                          |
|------------|----------------------------|-----------------------------------------|
| **HTTP**   | `src/app.py`               | Mount routes, health, metrics           |
| **Routes** | `src/api/routes/*.py`      | Validate input, CRUD, enqueue jobs        |
| **Schemas**| `src/api/schemas.py`       | JSON shapes in/out                      |
| **Models** | `src/models/*.py`          | Postgres tables                         |
| **Services** | `src/services/*.py`      | DB, queue, snapshots, secrets           |
| **Worker** | `src/workers/execution_worker.py` | Poll Redis → Steampipe → snapshot |
| **Scheduler** | `src/scheduler/cron_scheduler.py` | Due schedules → jobs → Redis   |

---

## 4. Database tables

All Stage 1 tables live in the **`public`** schema.

| Table              | Model file           | What it stores                          |
|--------------------|----------------------|-----------------------------------------|
| `tenants`          | `tenant.py`          | Customers, plan limits                  |
| `users`            | `user.py`            | Users per tenant                        |
| `api_keys`         | `api_key.py`         | API keys (auth optional via env)        |
| `cloud_accounts`   | `cloud_account.py`   | AWS/Azure/GCP account per tenant        |
| `queries`          | `query.py`           | Steampipe SQL + metadata                |
| `query_schedules`  | `query_schedule.py`  | Cron schedules (`run_all` supported)    |
| `execution_jobs`   | `execution_job.py`   | One job = one query × one account       |
| `execution_results`| `execution_result.py`| Outcome + `snapshot_path`               |
| `execution_batches`| `execution_batch.py` | Bulk / trigger-tenant run progress      |

### Migrations

| Migration | Adds |
|-----------|------|
| `001_initial_schema.py` | Core tables |
| `002_production_job_engine.py` | Batches, `batch_id`, `content_hash`, `run_all` schedules |
| `003_compliance_schema.py` | `compliance` schema (Stage 2) |
| `004_compliance_provider_category.py` | Provider/category on compliance tables |

Apply with:

```bash
./scripts/init_db.sh
# or
alembic upgrade head
```

### Entity relationships

```
Tenant
  ├── CloudAccount (many)
  ├── QuerySchedule (many)
  └── ExecutionJob (many)
        ├── CloudAccount (one)
        ├── Query (one)
        ├── ExecutionResult (one)
        └── ExecutionBatch (optional)
```

---

## 5. All APIs

**Base URL:** `http://localhost:8000`  
**API prefix:** `/api/v1`  
**Interactive docs:** `http://localhost:8000/docs`

### System endpoints (not under `/api/v1`)

| Method | Path       | Response / purpose              |
|--------|------------|---------------------------------|
| GET    | `/health`  | `{"status":"healthy"}`          |
| GET    | `/ready`   | Readiness probe                 |
| GET    | `/live`    | Liveness probe                  |
| GET    | `/metrics` | Prometheus metrics              |
| GET    | `/docs`    | Swagger UI                      |

---

### Tenants — `/api/v1/tenants`

| Method | Path                    | Body / query                         | What it does        |
|--------|-------------------------|--------------------------------------|---------------------|
| POST   | `/tenants`              | `{ name, plan_type, max_accounts, max_queries, max_executions_per_day, description? }` | Create customer |
| GET    | `/tenants`              | `?skip=0&limit=20&active=true`       | List tenants        |
| GET    | `/tenants/{tenant_id}`  | —                                    | Get one tenant      |

---

### Cloud accounts — `/api/v1/tenants/{tenant_id}/accounts`

| Method | Path                                      | Body / query              | What it does              |
|--------|-------------------------------------------|---------------------------|---------------------------|
| POST   | `/tenants/{tenant_id}/accounts`           | `{ provider, account_id, region?, name?, secret_arn?, extra_metadata? }` | Register cloud account |
| GET    | `/tenants/{tenant_id}/accounts`           | `?skip=0&limit=20&active=true` | List accounts for tenant |

**AWS assume-role:** Put `role_arn` and optional `external_id` in `extra_metadata`. Worker uses master AWS creds from `.env` to assume into the child account.

---

### Queries — `/api/v1/queries`

| Method | Path       | Body / query                    | What it does       |
|--------|------------|---------------------------------|--------------------|
| POST   | `/queries` | `{ name, version, provider, plugin, query_text, execution_mode, output_format, extra_metadata?, schedule_enabled? }` | Register query |
| GET    | `/queries` | `?provider=aws&active=true&skip=0&limit=20` | List queries |

**Query catalog:** 49 queries in `data/queries.json`. Load into DB with:

```bash
python scripts/apply_queries_document.py
```

Example `extra_metadata` on a compliance query:

```json
{
  "category": "compliance",
  "framework": "cis_aws_v6",
  "control_ref": "s3-public-access",
  "pass_rule": "zero_rows",
  "required_columns": ["name", "region"]
}
```

Stage 1 runs the SQL only. Metadata is used by Stage 2 (compliance evaluation).

---

### Schedules — `/api/v1/schedules`

| Method | Path         | Body / query                                              | What it does           |
|--------|--------------|-----------------------------------------------------------|------------------------|
| POST   | `/schedules` | `{ tenant_id?, query_id, cron_expression, timezone, enabled }` | Schedule query on cron |
| GET    | `/schedules` | `?tenant_id=...&enabled=true&skip=0&limit=20`             | List schedules         |

**Scheduler behavior** (`cron_scheduler.py`, every minute when `SCHEDULER_ENABLED=true`):

1. Find schedules where `enabled` and `next_run_at <= now()`
2. **Idempotency:** skip if batch already exists for `(schedule_id, scheduled_at)`
3. If `run_all=true`: create jobs for all active queries × all matching accounts
4. Else: one `query_id` × all accounts for that tenant (matching provider)
5. Create `ExecutionBatch`, jobs in chunks of 200 (`BULK_QUERY_IDS_MAX`)
6. Push each chunk to Redis; update `last_run_at` / `next_run_at`

---

### Executions — `/api/v1/executions`

| Method | Path                              | Body / query                         | What it does                          |
|--------|-----------------------------------|--------------------------------------|---------------------------------------|
| **POST** | `/executions`                   | `{ tenant_id, account_id, query_id, priority?, triggered_by? }` | **Run 1 query on 1 account** |
| POST   | `/executions/bulk`                | `{ tenant_id, account_id, query_ids: [...], priority?, triggered_by? }` | Many queries, one account (cap 200) |
| POST   | `/executions/trigger-tenant`      | `{ tenant_id, priority?, triggered_by? }` | All queries × all accounts for tenant |
| GET    | `/executions/batches/{batch_id}`  | —                                    | Batch progress                        |
| GET    | `/executions`                     | `?tenant_id=...&status=success&skip=0&limit=20` | List jobs                  |
| GET    | `/executions/{job_id}`            | —                                    | Job status + timestamps               |
| GET    | `/executions/{job_id}/result`     | —                                    | Result metadata (path, row_count)     |
| GET    | `/executions/{job_id}/result/data`| —                                    | **Actual JSON rows**                  |

**Job statuses:** `queued` → `running` → `success` | `failed` | `retrying`

**Trigger-tenant:** Enforces `tenant.max_executions_per_day`; returns `429` if exceeded.

---

## 6. End-to-end: one query run

### Step 1 — Setup (once)

```bash
cp env.example .env          # edit with your Postgres, Redis, AWS creds
./scripts/init_db.sh
python scripts/seed_dummy_data.py
python scripts/apply_queries_document.py
```

### Step 2 — Start the three processes

```bash
./scripts/run_api.sh         # terminal 1 → http://localhost:8000
./scripts/run_worker.sh      # terminal 2
./scripts/run_scheduler.sh   # terminal 3 (optional)
```

Or with Docker:

```bash
docker compose up -d
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_dummy_data.py
docker compose exec api python scripts/apply_queries_document.py
```

### Step 3 — Get IDs

```bash
curl http://localhost:8000/api/v1/tenants
curl http://localhost:8000/api/v1/tenants/{tenant_id}/accounts
curl "http://localhost:8000/api/v1/queries?provider=aws&active=true"
```

Pick a `tenant_id`, `account_id` (AWS), and `query_id` (provider must match).

### Step 4 — Enqueue execution

```bash
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "YOUR_TENANT_ID",
    "account_id": "YOUR_ACCOUNT_ID",
    "query_id": "YOUR_QUERY_ID"
  }'
```

Response:

```json
{
  "job_id": "...",
  "status": "queued",
  "created_at": "..."
}
```

### Step 5 — What happens internally

```
executions.py
  → INSERT execution_jobs (status=queued)
  → QueueService.push(job_id) → Redis key "steampipe:execution_jobs"

execution_worker.py
  → Redis BLPOP (blocking pop)
  → UPDATE job SET status=running WHERE id=? AND status IN (queued, retrying)  [atomic claim]
  → Load CloudAccount + Query from Postgres
  → Resolve credentials (env master creds + optional assume-role from account)
  → Write temporary .spc Steampipe connection file
  → steampipe query --output json "<query_text>"
  → SnapshotService.persist_snapshot() → file path or s3://...
  → INSERT execution_results (snapshot_path, row_count, duration_seconds)
  → UPDATE execution_jobs SET status=success
  → If batch_id set: update execution_batches completed_jobs / failed_jobs
```

On failure: retry up to `max_retries`, then `status=failed` with `error_message` in result.

### Step 6 — Read the result

```bash
# Job status
curl http://localhost:8000/api/v1/executions/{job_id}

# Metadata
curl http://localhost:8000/api/v1/executions/{job_id}/result

# Actual rows
curl http://localhost:8000/api/v1/executions/{job_id}/result/data
```

Example snapshot content:

```json
{
  "rows": [
    { "name": "my-bucket", "region": "us-east-1", "block_public_acls": false }
  ]
}
```

For compliance queries, rows typically represent **violations** (zero rows often means pass — evaluated in Stage 2).

---

## 7. Key services

### `src/services/queue.py` — Redis job queue

| Item    | Value                        |
|---------|------------------------------|
| Key     | `steampipe:execution_jobs`   |
| Push    | API, scheduler               |
| Pop     | Worker (`BLPOP`, 5s timeout) |
| Config  | `REDIS_URL` in `.env`        |

Supports Upstash (`rediss://`) and local Redis (`redis://localhost:6379/0`).

### `src/services/snapshot.py` — result storage

**Local** (`USE_LOCAL_STORAGE=true`):

```
./local/snapshots/{tenant_slug}/{provider}/{cloud_account_number}/{year}/{month}/{day}/{execution_id}/result.json
```

Example: `./local/snapshots/acme-corp/aws/387957186076/2026/06/20/bdb6af1d-.../result.json`

**S3** (`USE_LOCAL_STORAGE=false`):

```
s3://{S3_BUCKET}/{tenant_slug}/{provider}/{cloud_account_number}/{year}/{month}/{day}/{execution_id}/result.json
```

API reads snapshots via `GET /executions/{job_id}/result/data` using `SnapshotService.get_snapshot_content()`.

### `src/workers/execution_worker.py` — Steampipe runner

- Dedicated Steampipe install: `STEAMPIPE_CONFIG_DIR/worker_install` (port `9194` by default)
- Does not conflict with a user's default Steampipe on port 9193
- **One job = one account = one Steampipe connection**
- Master AWS creds: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optional `AWS_SESSION_TOKEN`
- Child account: assume-role via `cloud_accounts.extra_metadata.role_arn`
- Concurrency: `MAX_CONCURRENT_EXECUTIONS` (default 3)
- Init wait: `STEAMPIPE_CONNECTION_INIT_WAIT_SECONDS` (default 45)

### `src/scheduler/cron_scheduler.py` — timed runs

- Polls every minute
- Creates `ExecutionBatch` per schedule run
- Jobs in chunks of `BULK_QUERY_IDS_MAX` (default 200)
- Never executes Steampipe directly

### `src/services/query_hash.py` — content hash

- `content_hash` = SHA-256 of normalized `query_text`
- Set on query create and by `apply_queries_document.py`

---

## 8. Scripts reference

| Script                        | When to use                                      |
|-------------------------------|--------------------------------------------------|
| `scripts/init_db.sh`          | Apply all Alembic migrations                     |
| `scripts/seed_dummy_data.py`  | Dev tenants, users, accounts, sample queries     |
| `scripts/apply_queries_document.py` | Load/update 49 queries from `data/queries.json` |
| `scripts/run_api.sh`          | Start FastAPI on port 8000                       |
| `scripts/run_worker.sh`       | Start execution worker                           |
| `scripts/run_scheduler.sh`    | Start cron scheduler                             |
| `scripts/check_aws_connectivity.py` | Debug AWS credentials from `.env`           |
| `scripts/install_steampipe_cert.sh` | Install Steampipe CA cert (macOS)           |

---

## 9. Configuration (.env)

Copy from `env.example`. Key variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres connection (Supabase, local, Railway, etc.) |
| `REDIS_URL` | Job queue (Upstash, local Docker Redis) |
| `USE_LOCAL_STORAGE` | `true` = local snapshots; `false` = S3 |
| `LOCAL_STORAGE_PATH` | e.g. `./local/snapshots` |
| `S3_BUCKET`, `S3_REGION` | S3 when `USE_LOCAL_STORAGE=false` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Master AWS creds for worker |
| `STEAMPIPE_PATH` | Path to steampipe binary |
| `STEAMPIPE_CONFIG_DIR` | Worker Steampipe config dir |
| `STEAMPIPE_DATABASE_PORT` | Default `9194` |
| `STEAMPIPE_DATABASE_INSECURE` | `true` for local dev (skip TLS verify) |
| `MAX_CONCURRENT_EXECUTIONS` | Worker concurrency (default 3) |
| `SCHEDULER_ENABLED` | Enable cron scheduler |
| `BULK_QUERY_IDS_MAX` | Chunk size for bulk/trigger/scheduler (default 200) |
| `JWT_SECRET_KEY`, `API_AUTH_REQUIRED` | Auth (optional in dev) |

### Infrastructure options

| Setup | Postgres | Redis | Best for |
|-------|----------|-------|----------|
| **All local Docker** | `docker-compose.yml` postgres | same compose redis | First-time setup, reset easily |
| **Hybrid (recommended dev)** | Supabase | Upstash or local Redis | Persistent data, real DB |
| **All remote** | Supabase / Railway | Upstash / Railway | Staging, shared team env |

**Note:** Supabase provides Postgres only — Redis must always come from elsewhere (Upstash, Docker, Railway).

**Supabase tip:** Use the **direct** connection (port 5432) for Alembic migrations; add `?sslmode=require` if needed.

**Security:** Never commit `.env` to git. Rotate credentials if exposed.

---

## 10. How to run

**Using remote Postgres (Supabase) + Redis (Upstash) with no local DB containers?**  
See **[RUN_WITH_REMOTE_DB.md](RUN_WITH_REMOTE_DB.md)**. Use:

```bash
docker compose -f docker-compose.remote.yml up
```

Do **not** use plain `docker compose up` — it overrides your `.env` URLs with local Postgres/Redis.

### Option A — Docker (full local stack)

```bash
docker compose up -d
docker compose exec api alembic upgrade head
docker compose exec api python scripts/seed_dummy_data.py
docker compose exec api python scripts/apply_queries_document.py
```

API: http://localhost:8000/docs

Stop:

```bash
docker compose down
# Wipe DB volumes:
docker compose down -v
```

### Option B — Docker (remote DB only)

Api + worker + scheduler only; `DATABASE_URL` and `REDIS_URL` from `.env`:

```bash
docker compose -f docker-compose.remote.yml build
docker compose -f docker-compose.remote.yml up
```

### Option C — Remote DB + Redis, local processes

Requires **Python 3.11+** (project uses `str | None` syntax).

```bash
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./scripts/init_db.sh
python scripts/seed_dummy_data.py
python scripts/apply_queries_document.py

./scripts/run_api.sh        # terminal 1
./scripts/run_worker.sh     # terminal 2
./scripts/run_scheduler.sh  # terminal 3
```

### Option D — Postgres + Redis in Docker, app locally

```bash
docker compose -f docker-compose.local.yml up -d
# .env:
#   DATABASE_URL=postgresql://steampipe:steampipe@localhost:5432/steampipe
#   REDIS_URL=redis://localhost:6379/0
# then run Option B scripts
```

### Verify it works

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/tenants
```

Enqueue a job and watch worker logs:

```bash
docker compose logs -f worker
# or check terminal running run_worker.sh
```

---

## 11. Stage 2 (brief)

Stage 2 lives in `cloud-compliance-engine/` — a **separate FastAPI app** that consumes Stage 1 snapshots.

```
Stage 1 output                    Stage 2 (not fully wired yet)
────────────────                  ─────────────────────────────
snapshot JSON (S3/local)    →     extract → compliance.execution_snapshot_rows
execution_results.snapshot_path   evaluate → control_results (PASS/FAIL)
queries.extra_metadata            CIS v6 rules from config/catalog
```

Stage 2 is **not** started by Stage 1 automatically yet. See `cloud-compliance-engine/README.md` and `cloud-compliance-engine/RUNBOOK.md`.

---

## 12. Quick reference

| Question | Answer |
|----------|--------|
| Where is the API? | `src/app.py` + `src/api/routes/` |
| Where is Steampipe run? | `src/workers/execution_worker.py` **only** |
| Where are queries defined? | `data/queries.json` → `queries` table |
| Where are results stored? | JSON files (local/S3); path in `execution_results` |
| What connects API to worker? | Redis queue `steampipe:execution_jobs` |
| What stores config/metadata? | Postgres |
| How do I run one query? | `POST /api/v1/executions` |
| How do I get rows back? | `GET /api/v1/executions/{job_id}/result/data` |
| How do I run everything for a tenant? | `POST /api/v1/executions/trigger-tenant` |
| How do I schedule recurring runs? | `POST /api/v1/schedules` + running scheduler |

### Stage 1 flow (one line)

```
POST /executions → Redis → Worker → Steampipe → AWS → Snapshot + Postgres → GET /result/data
```

---

## Related docs

| Doc | Topic |
|-----|-------|
| [README.md](../README.md) | Quick start |
| [LOCAL_DEVELOPMENT.md](../LOCAL_DEVELOPMENT.md) | Migrations, seed, run flow |
| [Testing.md](../Testing.md) | pytest, service testing |
| [prompt.md](../prompt.md) | Full original spec |
| [PLAN_AND_IMPLEMENTATION_SUMMARY.md](PLAN_AND_IMPLEMENTATION_SUMMARY.md) | Plan vs implemented |
| [CODE_STATUS_AND_FEATURES_TO_ADD.md](CODE_STATUS_AND_FEATURES_TO_ADD.md) | Feature checklist |
| [FRESH_DB_SETUP.md](../FRESH_DB_SETUP.md) | Reset local DB |
| [RUN_WITH_REMOTE_DB.md](RUN_WITH_REMOTE_DB.md) | Supabase + Upstash, no local Postgres/Redis |
| [SCALING_ROADMAP.md](SCALING_ROADMAP.md) | Phases 0–4: scale workers, warm Steampipe, bulk sessions |
| [cloud-compliance-engine/README.md](../cloud-compliance-engine/README.md) | Stage 2 |
