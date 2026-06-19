# Cloud Governance & Cost Intelligence Platform

## Project objective

Build a **production-ready**, **horizontally scalable**, **multi-tenant** Cloud Governance & Cost Intelligence Platform powered by Steampipe.

The system must:

- Execute Steampipe SQL & benchmark queries
- Support **AWS**, **Azure**, **GCP**, **Kubernetes**, **GitHub**, **GitLab**, **Terraform**
- Be fully multi-tenant isolated
- Use **async job queue architecture** (API must never block)
- Store snapshots in **S3** (data-lake partitioned structure)
- Provide **REST API** (FastAPI)
- Support **JWT + API key** authentication
- Support **per-query cron scheduling** and **run-all** schedules (one schedule runs all queries × all accounts for a tenant)
- Be SaaS monetization ready
- Be production-grade and cloud-native

---

## Architecture overview

The system must be split logically into:

| Layer | Description |
|-------|-------------|
| **API Service** | REST API only; no Steampipe execution |
| **Execution Worker** | Runs Steampipe; consumes job queue |
| **Scheduler Service** | Cron-based job creation |
| **Database Layer** | PostgreSQL + SQLAlchemy |
| **Snapshot Storage Layer** | S3 (partitioned) |
| **Secrets Manager Layer** | Credential resolution |
| **Job Queue Layer** | Redis (see user_input.md for URL) |

**Rule:** The API must **NOT** execute Steampipe directly.

**Infrastructure:** Use **remote** PostgreSQL, Redis, and S3 only. No local DB/Redis for production. Connection details and env vars → see **user_input.md**.

---

## For Cursor: implementing from scratch

When building the codebase from scratch in Cursor, use these three files together:

| File | Purpose |
|------|---------|
| **prompt.md** (this file) | Full spec, schema, architecture, rules |
| **user_input.md** | Canonical `.env` values: remote Postgres URL, Redis URL, S3 bucket/region/keys, JWT, feature flags |
| **Testing.md** | How to run API/worker/scheduler and run tests |
| **LOCAL_DEVELOPMENT.md** | Migrations workflow, seed script, local setup (init_db → seed → run API/Worker/Scheduler) |

**Implementation order:** (1) `config` + env from user_input.md → (2) `models` → (3) Alembic migrations → (4) `services` (snapshot, secrets, queue) → (5) `api` routes → (6) `workers` execution worker → (7) `scheduler` → (8) `scripts/` and README. Assume **Redis** for the job queue and **S3** for snapshots (no SQS or local-storage branching in core paths).

---

## Core design principles

- Strict tenant isolation
- Non-blocking API
- Async execution via job queue
- Concurrency limits
- Clean separation of **ExecutionJob**, **ExecutionResult**, and **ExecutionBatch**
- Partitioned data lake snapshot storage (tenant, provider, account_id, date, execution_id)
- Per-query scheduling and **run-all** schedules (run_all + nullable query_id)
- Trigger-for-tenant (all queries × all accounts) with daily limit and batch progress
- Enterprise RBAC-ready
- Soft delete support
- Observability and metrics enabled

---

## Project structure

```
project_root/
├── .env
├── env.example
├── requirements.txt
├── Dockerfile
├── alembic.ini
├── README.md
├── scripts/
│   ├── init_db.sh
│   ├── seed_dummy_data.py
│   ├── apply_queries_document.py   # apply data/queries.json to queries table (sets content_hash)
│   ├── run_api.sh
│   ├── run_worker.sh
│   ├── run_scheduler.sh
├── alembic/
│   ├── env.py
│   └── versions/
├── data/
│   └── queries.json              # query catalog; apply via scripts/apply_queries_document.py
├── src/
│   ├── app.py
│   ├── config.py
│   ├── config/settings.py
│   ├── cli.py
│   ├── api/
│   ├── models/
│   ├── services/
│   │   ├── snapshot.py           # S3/local; path: tenant_id/provider/account_id/date/execution_id/result.json
│   │   ├── query_hash.py         # content_hash = SHA-256(normalized query_text)
│   │   ├── queue.py
│   │   └── ...
│   ├── workers/
│   ├── scheduler/
│   └── utils/
```

---

## Database design (PostgreSQL 12+)

Use **SQLAlchemy 2.0** + **Alembic**.

### Enums

| Enum | Values |
|------|--------|
| **CloudProvider** | `aws`, `azure`, `gcp`, `kubernetes`, `github`, `gitlab`, `terraform` |
| **ExecutionJobStatus** | `queued`, `running`, `retrying`, `success`, `failed` |
| **ExecutionResultStatus** | `success`, `failed`, `timeout` |
| **UserRole** | `super_admin`, `tenant_admin`, `tenant_user`, `viewer` |

### Core tables

#### Tenant

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `name` | unique |
| `description` | text |
| `plan_type` | free, pro, enterprise |
| `max_accounts` | int |
| `max_queries` | int |
| `max_executions_per_day` | int |
| `active` | bool |
| `deleted_at` | soft delete |
| `created_at`, `updated_at` | timestamps |

#### User

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `tenant_id` | FK |
| `email` | unique |
| `username` | text |
| `hashed_password` | text |
| `role` | UserRole |
| `permissions` | JSONB |
| `active` | bool |
| `last_login` | timestamp |
| `created_at`, `updated_at` | timestamps |

#### APIKey

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `tenant_id` | FK |
| `key_hash` | unique |
| `key_prefix` | text |
| `active` | bool |
| `expires_at` | timestamp |
| `last_used_at` | timestamp |
| `created_at`, `updated_at` | timestamps |

#### CloudAccount

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `tenant_id` | FK |
| `provider` | CloudProvider |
| `account_id` | text |
| `region` | text |
| `name` | text |
| `secret_arn` | text |
| `active` | bool |
| `extra_metadata` | JSONB |
| `deleted_at` | soft delete |
| `created_at`, `updated_at` | timestamps |

**Unique:** `(tenant_id, provider, account_id)`

#### Query

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `name` | text |
| `version` | text |
| `provider` | CloudProvider |
| `plugin` | text |
| `query_text` | text |
| `content_hash` | varchar(64), SHA-256 of normalized query_text (set by apply script and query create API) |
| `execution_mode` | single_account, multi_account, multi_region |
| `output_format` | json, csv |
| `schedule_enabled` | bool |
| `active` | bool |
| `extra_metadata` | JSONB |
| `deleted_at` | soft delete |
| `created_at`, `updated_at` | timestamps |

**Unique:** `(name, version)`

#### QuerySchedule

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `tenant_id` | FK |
| `query_id` | FK nullable (null when run_all=true) |
| `cron_expression` | text |
| `timezone` | text |
| `enabled` | bool |
| `run_all` | bool default false; when true, run all queries × all accounts for tenant |
| `last_run_at` | timestamp |
| `next_run_at` | timestamp |
| `created_at`, `updated_at` | timestamps |

#### ExecutionBatch

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `tenant_id` | FK |
| `schedule_id` | FK nullable (null for manual trigger-tenant) |
| `scheduled_at` | timestamp nullable |
| `trigger_type` | manual \| schedule |
| `total_jobs` | int |
| `completed_jobs` | int |
| `failed_jobs` | int |
| `status` | running \| completed \| failed \| partial |
| `created_at` | timestamp |
| `finished_at` | timestamp nullable |

Created by trigger-tenant or scheduler; worker updates completed_jobs/failed_jobs and status when jobs finish.

#### ExecutionJob (task)

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `tenant_id` | FK |
| `account_id` | FK |
| `query_id` | FK |
| `batch_id` | FK nullable (set for trigger-tenant and scheduled batch runs) |
| `priority` | int |
| `status` | ExecutionJobStatus |
| `retry_count` | int |
| `max_retries` | int |
| `triggered_by` | text |
| `triggered_by_user` | FK (optional) |
| `scheduled_at` | timestamp |
| `started_at` | timestamp |
| `finished_at` | timestamp |
| `created_at`, `updated_at` | timestamps |

#### ExecutionResult (output)

| Column | Type / Notes |
|--------|------------------|
| `id` | UUID PK |
| `execution_job_id` | FK |
| `status` | ExecutionResultStatus |
| `row_count` | int |
| `duration_seconds` | float |
| `snapshot_path` | text |
| `error_message` | text |
| `steampipe_version` | text |
| `plugin_version` | text |
| `connection_name` | text |
| `created_at` | timestamp |

---

## Database schema & migrations

Schema changes are **explicit only**. No automatic schema alteration at runtime.

| Rule | Description |
|------|-------------|
| **Migrations** | Only `./scripts/init_db.sh` or `alembic upgrade head` apply migrations. |
| **API / Worker / Scheduler** | Assume the DB schema is up-to-date. They do **not** check or change the schema at runtime. |
| **Missing table/column** | If schema is out of date, services fail with an error—this signals that a migration must be run. |

**Workflow when models change:**

1. Create migration: `alembic revision --autogenerate -m "Add new column to Query"`
2. Apply: `alembic upgrade head`
3. Then run API / Worker / Scheduler; they use the updated schema.

**init_db.sh** must: create tables if missing and run `alembic upgrade head` so the schema is up-to-date. Migrations: **001** initial schema (tenants, accounts, queries, query_schedules, execution_jobs, execution_results); **002** production job engine (execution_batches, execution_jobs.batch_id, queries.content_hash, query_schedules.run_all and nullable query_id, indexes). In production, run migrations per environment (e.g. via CI/CD) before deploying code; do not run migrations from the scheduler.

---

## Execution flow

### API behavior

- **POST /executions** (single): Validate tenant and limits; create one `ExecutionJob` (no batch_id); push to Redis; return job_id.
- **POST /executions/bulk**: Many query_ids, one account; create one job per query; cap at `BULK_QUERY_IDS_MAX` (default 200); no batch_id.
- **POST /executions/trigger-tenant**: Body `{ tenant_id }`. Load active accounts and active queries; build (account, query) pairs where account.provider == query.provider; enforce `tenant.max_executions_per_day` (return 429 if exceeded); create one `ExecutionBatch` (trigger_type=manual); create jobs in chunks of 200 with batch_id; push each chunk to Redis; return batch_id, total_jobs, accounts_count, queries_count.
- **GET /executions/batches/{batch_id}**: Return batch progress (total_jobs, completed_jobs, failed_jobs, status, finished_at).
- **GET /executions**, **GET /executions/{job_id}**, **GET /executions/{job_id}/result**, **GET /executions/{job_id}/result/data**: List/filter jobs, get job detail, get result, get snapshot JSON.
- **Rule:** API must **never** run Steampipe.

### Worker behavior

The worker service must:

1. Poll queue (Redis blpop).
2. **Atomic claim:** `UPDATE execution_jobs SET status='running', started_at=now() WHERE id=job_id AND status IN ('queued','retrying')`; commit; if rowcount 0 skip; else reload job and continue.
3. Acquire concurrency semaphore, fetch credentials, generate temporary `.spc`, run `steampipe query --output json`.
4. Persist snapshot to S3 (partitioned path includes tenant_id, provider, account_id, date, execution_id).
5. Create `ExecutionResult`; update job status to success or failed.
6. **Batch update:** If job.batch_id is set, call _update_batch_on_job_finish(session, batch_id, success): increment completed_jobs or failed_jobs; when completed_jobs + failed_jobs >= total_jobs set batch status (completed/failed/partial) and finished_at.
7. **Retry:** On failure, if retry_count < max_retries: set status=queued, increment retry_count, commit, push job back to queue; else mark failed, create ExecutionResult, update batch, commit.
8. Enforce max concurrency.

**Environment:** `MAX_CONCURRENT_EXECUTIONS`, `BULK_QUERY_IDS_MAX` (chunk size; default 200).

---

## Snapshot storage design

Partitioned S3 layout (path includes tenant, provider, account_id, date, and execution_id for listing and debugging):

```
s3://bucket/
  tenant_id=uuid/
    provider=aws/
      account_id=uuid/
        year=YYYY/
          month=MM/
            day=DD/
              execution_id=uuid/
                result.json
```

- Must support **local fallback** for development (same key structure under LOCAL_STORAGE_PATH).

---

## Scheduler design

- Use **APScheduler**.
- **Every minute:**
  1. Fetch `QuerySchedule` where `enabled` and `next_run_at <= now()`.
  2. **Idempotency:** Skip if an `ExecutionBatch` already exists for the same `schedule_id` and `scheduled_at`.
  3. **run_all:** If `query_schedules.run_all` is true, load all active queries and build (account, query) pairs by provider for the tenant; else use the schedule’s single `query_id` and create one job per account.
  4. Create one `ExecutionBatch` per run (schedule_id, scheduled_at, trigger_type=schedule).
  5. Create jobs in chunks of 200 (BULK_QUERY_IDS_MAX) with batch_id; push each chunk to queue; commit per chunk.
  6. Update `last_run_at` and `next_run_at` from cron.
- **Rule:** Scheduler must **not** execute queries directly.

---

## Authentication

Support:

- **JWT authentication**
- **API key authentication**
- Optional auth disable via env

Implement:

- Access token
- Token expiration
- Password hashing (bcrypt)
- API key hashing
- Tenant-scoped access enforcement

---

## Security requirements

- Require strong JWT secret in production
- Rate limiting per tenant
- Request ID middleware
- Security headers middleware
- No secret logging
- Temporary file cleanup for `.spc`

---

## Observability

Add:

- Structured JSON logging
- Execution duration logging
- **Prometheus metrics** endpoint: `/metrics`

Track:

- `execution_total{status}`
- `execution_duration_seconds`
- `active_jobs`
- `queue_depth`

---

## Configuration

All config via **environment variables**. Support:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection (postgresql://, see user_input.md) |
| `REDIS_URL` | Redis connection for job queue (see user_input.md) |
| S3 bucket config | Snapshot storage (bucket, region, keys; see user_input.md) |
| AWS credentials | S3 / Secrets Manager |
| `STEAMPIPE_PATH` | Steampipe binary |
| `STEAMPIPE_INSTALL_DIR` | Install directory |
| `STEAMPIPE_CONFIG_DIR` | Config directory |
| `MAX_CONCURRENT_EXECUTIONS` | Worker concurrency |
| `BULK_QUERY_IDS_MAX` | Chunk size for trigger-tenant and scheduler (default 200) |
| `SCHEDULER_ENABLED` | Enable scheduler |
| `RATE_LIMIT_PER_MINUTE` | Per-tenant rate limit |
| `JWT_SECRET_KEY` | JWT signing |
| `API_AUTH_REQUIRED` | Require auth |

- Normalize `postgres://` to `postgresql://`.

---

## API endpoints

**Base path:** `/api/v1`

| Resource | Methods |
|----------|--------|
| **Tenants** | `POST /tenants`, `GET /tenants`, `GET /tenants/{tenant_id}` |
| **Accounts** | `POST /tenants/{tenant_id}/accounts`, `GET /tenants/{tenant_id}/accounts` |
| **Queries** | `POST /queries`, `GET /queries` (responses include optional `content_hash`) |
| **Schedules** | `POST /schedules`, `GET /schedules` |
| **Executions** | `POST /executions` (single), `POST /executions/bulk`, `POST /executions/trigger-tenant`, `GET /executions/batches/{batch_id}` (batch progress), `GET /executions`, `GET /executions/{job_id}`, `GET /executions/{job_id}/result`, `GET /executions/{job_id}/result/data` |

- Must support **filtering** (e.g. tenant_id, status for executions) and **pagination**.

---

## Concurrency control

Worker must:

- Limit concurrent executions
- Prevent system overload
- Retry failed jobs
- Respect `max_executions_per_day` per tenant

---

## Docker requirements

Dockerfile must:

- Use **Python 3.11**
- Install **Steampipe**
- Install plugins on startup
- Expose API port
- Support worker mode via ENV

---

## Dummy data / seed script

Provide **scripts/seed_dummy_data.py** to seed a dev or test DB with safe dummy data. Use a **separate** local or dev DB (or test DB); never seed production.

**Seed:**

- 2–3 **tenants** (e.g. free, pro, enterprise) with distinct `plan_type`, `max_accounts`, `max_queries`, `max_executions_per_day`
- 2–3 **users** per tenant (e.g. tenant_admin, tenant_user), with hashed passwords (bcrypt)
- 2–3 **cloud accounts** per tenant (e.g. AWS, Azure, GCP) with `provider`, `account_id`, `region`, `name`
- 2–3 **queries** per tenant (e.g. `list_ec2_instances`, `list_azure_vms`) with `query_text`, `provider`, `plugin`, `execution_mode`, `output_format`
- Optional: **QuerySchedule** entries for some queries

Preserve **tenant isolation**: all users and accounts must reference the correct `tenant_id`. Optional: use **Faker** for realistic random data (e.g. company names, regions).

**How to run:** After `./scripts/init_db.sh`, run `python scripts/seed_dummy_data.py`. Tests can use the same script or fixtures to pre-populate tenants, users, accounts, and queries; snapshot storage in tests can use a local path to avoid S3.

---

## Implementation requirements

- Use **SQLAlchemy 2** style
- Use **Pydantic v2**
- Use **Alembic** migrations
- Use **dependency injection** patterns
- No blocking calls inside API
- No global state leakage
- Clean error handling
- **Fully typed** code (Python typing)

---

## Important rules

| Rule | Description |
|------|-------------|
| API | Never executes Steampipe |
| Scheduler | Never executes Steampipe |
| Worker | Only component that executes Steampipe |
| Model split | `ExecutionJob` ≠ `ExecutionResult`; batches use `ExecutionBatch` + `ExecutionJob.batch_id` |
| Tenant | Always enforce tenant isolation; trigger-tenant respects max_executions_per_day |
| S3 | Always partition by tenant, provider, account_id, date; path includes execution_id |
| Config | Always use temporary connection config |
| Cleanup | Always clean up temp files |
| DB | Always commit/rollback sessions safely; worker uses atomic claim (UPDATE then commit) |

---

## Final goal

When complete, the system must:

- Serve `/docs` (OpenAPI/Swagger)
- Serve `/health`, `/ready`, `/live`
- Queue execution jobs (single, bulk, trigger-tenant with batch)
- Expose batch progress via `GET /executions/batches/{batch_id}`
- Run worker independently (atomic claim, retry/requeue, batch completion updates)
- Execute Steampipe queries safely
- Store snapshots in S3 (path includes tenant, provider, account_id, date, execution_id)
- Schedule queries via cron (per-query and run_all; idempotent; chunks of 200)
- Enforce plan limits (max_executions_per_day on trigger-tenant)
- Be horizontally scalable

---

## Output expectation

Generate **full production-ready code** for:

- All modules
- All migrations
- All models
- All services
- All workers
- All API routes
- All config
- All scripts
- README with setup instructions; **LOCAL_DEVELOPMENT.md** for migrations, dummy data, and local run (see that file for the full flow)

**Deployable with:**

```bash
docker build .
docker run ...
```

**Runnable locally with:**

```bash
./scripts/init_db.sh
./scripts/run_api.sh
./scripts/run_worker.sh
./scripts/run_scheduler.sh
```
