# Local Development Guide

This guide covers **database migrations**, **dummy data seeding**, and **running the app locally** (API, Worker, Scheduler). Use it for local dev and to keep the schema in sync across dev, staging, and production.

---

## 1. How DB schema changes are handled

The project uses **PostgreSQL + SQLAlchemy + Alembic**. Schema changes are **explicit only**.

| Question | Answer |
|----------|--------|
| Does schema change on every run? | **No.** Only via Alembic migrations. |
| Can Worker/API create tables automatically? | **No.** They assume the schema exists. If a table/column is missing, they fail—that means a migration is required. |
| How to keep local dev DB in sync? | Run `./scripts/init_db.sh` (creates tables + runs all migrations). |
| Production DB? | Apply migrations manually or via CI/CD **before** deploying new code. |

### Rules

- **Never** automatically alter the database schema when the API or Worker runs.
- **Only** `./scripts/init_db.sh` or `alembic upgrade head` apply migrations.
- API, Worker, and Scheduler **assume** the DB schema is up-to-date; they do not check or change it at runtime.

---

## 2. Recommended workflow for migrations

When you change SQLAlchemy models:

1. **Create a migration**
   ```bash
   alembic revision --autogenerate -m "Add new column to Query"
   ```

2. **Apply it to the DB**
   ```bash
   alembic upgrade head
   ```

3. **Then** run API / Worker / Scheduler—they will use the updated schema.

For a multi-tenant SaaS, run migrations **per environment** (staging, production) and **do not** run them from the hourly scheduler.

---

## 3. Local development: first-time setup

When a developer clones the repo and uses the **remote** Postgres/Redis/S3 from **user_input.md**:

1. **Copy env**
   - Create `.env` from **user_input.md** (DATABASE_URL, REDIS_URL, S3_*, JWT_SECRET_KEY, etc.).

2. **Init DB and run migrations**
   ```bash
   ./scripts/init_db.sh
   ```
   This creates tables (if missing) and runs `alembic upgrade head` so the schema is up-to-date.

3. **Seed dummy data (optional but recommended)**
   ```bash
   python scripts/seed_dummy_data.py
   ```
   Seeds tenants, users, cloud accounts, and queries for local testing.
   If your `.env` points at a remote DB (e.g. Railway) and you get `could not translate host name ... to address`, either ensure the host is reachable (network/DNS) or seed a **local** Postgres instead:
   ```bash
   SEED_DATABASE_URL=postgresql://localhost/steampipe python scripts/seed_dummy_data.py
   ```
   (Run migrations against that DB first, e.g. `DATABASE_URL=postgresql://localhost/steampipe ./scripts/init_db.sh`.)

4. **Run the three processes** (see [Run API, Worker, Scheduler](#4-run-api-worker-scheduler)).

If two developers use the **same** remote DB, migrations need to run only once; Alembic tracks applied migrations in the `alembic_version` table.

---

## 4. Run API, Worker, Scheduler

You need **three** processes. Use three terminals (or run in background).

| Process | Command | Purpose |
|---------|---------|---------|
| **API** | `./scripts/run_api.sh` | Serves `/docs`, `/health`, `/ready`, `/live`, REST API. |
| **Worker** | `./scripts/run_worker.sh` | Polls Redis for jobs, runs Steampipe, writes snapshots to S3. |
| **Scheduler** | `./scripts/run_scheduler.sh` | Polls `QuerySchedule`, enqueues execution jobs (no Steampipe). |

After this, the app is running locally against your remote Postgres, Redis, and S3.

### Run with Docker (Linux; .env loaded)

To run API, worker, and scheduler in containers (avoids macOS Steampipe cert/keychain issues):

1. Create `.env` (same as above; `DATABASE_URL`, `REDIS_URL`, S3 or `USE_LOCAL_STORAGE`, etc.).
2. From the project root:
   ```bash
   docker compose build
   docker compose up
   ```
3. API is at http://localhost:8000. Worker and scheduler run in separate containers; all use `env_file: .env`. The worker uses the image’s Steampipe install at `/app/steampipe/worker_install` (AWS plugin pre-installed; Linux only).

---

## 5. Execute a query and get results (flow)

To run a Steampipe query and get results end-to-end:

### Prerequisites

- **API**, **Worker**, and **Scheduler** are running (see [§4](#4-run-api-worker-scheduler)).
- **Steampipe** is installed; the worker runs `steampipe query` (see [§7](#7-full-local-mvp-flow-checklist)).
- You have at least one **tenant**, **cloud account**, and **query** (e.g. from `python scripts/seed_dummy_data.py`).

### Step 1: Get IDs

You need a `tenant_id`, an `account_id`, and a `query_id` that belong together (account must be for that tenant; query can be any registered query).

- **Tenants:** `GET /api/v1/tenants` → pick an `id`.
- **Accounts for that tenant:** `GET /api/v1/tenants/{tenant_id}/accounts` → pick an `id` (e.g. AWS account for that tenant).
- **Queries:** `GET /api/v1/queries` → pick a `query_id` whose `provider` matches the account (e.g. `aws` query for an AWS account).

### Step 2: Create an execution

- **Request:** `POST /api/v1/executions`  
- **Body (JSON):**
  ```json
  {
    "tenant_id": "<tenant_id>",
    "account_id": "<account_id>",
    "query_id": "<query_id>"
  }
  ```
- **Response:** `{ "job_id": "...", "status": "queued", "created_at": "..." }`. Save `job_id`.

### Step 3: What happens next (flow)

1. **API** creates an `ExecutionJob` (status `queued`) and pushes `job_id` to **Redis**.
2. **Worker** (running `./scripts/run_worker.sh`) pops the job from Redis, loads the job, account, and query from the DB.
3. Worker runs **Steampipe** (`steampipe query --output=json <query_text>`) with the account’s connection/credentials.
4. Worker writes the result JSON to a **snapshot** (local path if `USE_LOCAL_STORAGE=true`, else S3), then creates an **ExecutionResult** and sets the job status to `success` or `failed`.

### Step 4: Check job status and result metadata

- **Job status:** `GET /api/v1/executions/{job_id}`  
  - Returns status (`queued` → `running` → `success` or `failed`), timestamps, etc.
- **Result metadata:** `GET /api/v1/executions/{job_id}/result`  
  - Returns `row_count`, `duration_seconds`, `snapshot_path`, `error_message` (if failed).  
  - When status is `success`, the actual rows are stored at `snapshot_path`.

### Step 5: Get the actual result data (rows)

- **Result JSON (rows):** `GET /api/v1/executions/{job_id}/result/data`  
  - Returns the snapshot content (Steampipe result JSON: list of rows or `{ "rows": [...] }`).  
  - Use this to get the query results without reading files or S3.

**Summary:** Create execution → Worker runs Steampipe → Snapshot saved → Get status via `GET /executions/{job_id}` and `GET /executions/{job_id}/result`, and the rows via `GET /executions/{job_id}/result/data`.

### Architecture: multi-account / assume-role (how this project fits)

This API is **multi-tenant**: each execution targets **one** cloud account (from the DB). We do **not** run a single Steampipe service with many connections and an `aws_all` aggregator. Instead:

- **One job = one account = one connection.** Connection config comes from `CloudAccount` + secrets (e.g. `secret_arn`, `extra_metadata`), not from a static accounts file.
- **AWS assume-role:** If the account has `role_arn` (and optionally `external_id`), the worker builds a temp AWS profile that assumes that role; master credentials come from env (`AWS_ACCESS_KEY_ID` etc.) where the worker runs. So “master account gets data from child” is supported **per execution** (one child per job), not via one shared service with multiple connections.
- **Worker Steampipe:** The worker uses a dedicated install dir (`STEAMPIPE_CONFIG_DIR/worker_install`) and port (`STEAMPIPE_DATABASE_PORT`, default 9194) so it never conflicts with a user’s default Steampipe on 9193.

If you later want “query all accounts in one SQL” (e.g. `aws_all.aws_account`), that would mean either a different job type that builds an aggregator config and one query, or a separate service that runs the “multi-account generator” pattern (accounts file → generated connections + aws_all) and is queried by this API.

---

## 6. Dummy data strategy

Dummy data is for **local dev and tests only**. Use a **separate** DB (e.g. dev or test); never seed production.

### What gets seeded

- **2–3 tenants** (e.g. free, pro, enterprise) with plan limits.
- **2–3 users per tenant** (e.g. admin, user) with hashed passwords (e.g. `password123`).
- **2–3 cloud accounts per tenant** (e.g. AWS, Azure, GCP) with provider, region, name.
- **2–3 queries per tenant** (e.g. `list_ec2_instances`, `list_azure_vms`) with SQL and plugin.
- **Optional:** QuerySchedule entries for some queries.

Tenant isolation is preserved: all users and accounts reference the correct `tenant_id`.

### How to run

```bash
# After DB is migrated
./scripts/init_db.sh
python scripts/seed_dummy_data.py
```

### Using dummy data in tests

- Point tests at a **test DB** (or same dev DB).
- Use the seed script as a fixture to pre-populate tenants, users, accounts, and queries.
- Use **local filesystem** for snapshot storage in tests to avoid S3 (e.g. `SnapshotService(use_local_storage=True, local_storage_path=tmp_path)`).

Optional: use the **Faker** library for more realistic random data (emails, company names, regions).

---

## 7. Schema stability summary

| Topic | Detail |
|-------|--------|
| Schema changes at runtime | **None.** Only migrations change schema. |
| New features | Require: (1) SQLAlchemy model change, (2) Alembic migration, (3) apply migration before deploying. |
| Local dev in sync | `./scripts/init_db.sh` → tables + all migrations. |
| Production | Apply migrations (manually or CI/CD) before deploying new code. |

---

## 8. Full local MVP flow (checklist)

1. **Env** – `.env` from **user_input.md** (remote Postgres, Redis, S3).
2. **Steampipe** – Installed locally; plugins: `steampipe plugin install aws azure gcp kubernetes github gitlab terraform`.
3. **Python** – `python3.11 -m venv venv`, `source venv/bin/activate`, `pip install -r requirements.txt`.
4. **DB** – `./scripts/init_db.sh`.
5. **Seed** – `python scripts/seed_dummy_data.py`.
6. **Run** – `./scripts/run_api.sh`, `./scripts/run_worker.sh`, `./scripts/run_scheduler.sh` (three terminals).
7. **Test** – Open `http://localhost:8000/docs`, get IDs from `GET /tenants`, `GET /tenants/{id}/accounts`, `GET /queries`, then call `POST /executions` with those IDs; poll `GET /executions/{job_id}` and get rows from `GET /executions/{job_id}/result/data` (see [§5](#5-execute-a-query-and-get-results-flow)).

This gives a fully functional local MVP against your remote infrastructure.

### Execution failed: "x509: certificate signed by unknown authority"

The Steampipe CLI connects to its local service (127.0.0.1:9193) over TLS. Your system doesn’t trust Steampipe’s CA, so the connection fails.

**Option A — Install Steampipe’s root certificate (recommended, one-time):**

```bash
./scripts/install_steampipe_cert.sh
```

This finds `root.crt` under `~/.steampipe/db` and adds it to the macOS system keychain. You’ll be prompted for your password. Then restart the worker and run an execution again.

**Option B — Try disabling TLS via env (may not work on all Steampipe versions):**

Add to `.env`: `STEAMPIPE_DATABASE_INSECURE=true`, restart the worker, and check the first log line for `STEAMPIPE_DATABASE_INSECURE=True`. If the error persists, use Option A.

**Worker note (macOS):** On macOS, the worker uses your **existing** `~/.steampipe` install dir so the Steampipe client uses the same certificate you already trust (from normal Steampipe use). The worker temporarily sets the database port to 9194 in `~/.steampipe/config/default.spc` for the run, then restores your previous content. No keychain or cert script is required for the worker on macOS when you already use Steampipe locally. On Linux, the worker uses `STEAMPIPE_CONFIG_DIR/worker_install` and sets `SSL_CERT_FILE` to that install’s `root.crt`.
