# Fresh Database & Redis Setup

Use this when your Postgres and Redis are down (e.g. Railway credentials expired) and you need a clean local setup.

---

## Quick start (local Postgres + Redis)

### 1. Start local Postgres and Redis

```bash
cd /Users/deva/steampipe
docker compose -f docker-compose.local.yml up -d
```

Wait ~10 seconds for health checks, then verify:

```bash
docker compose -f docker-compose.local.yml ps
# Both postgres and redis should show "healthy"
```

### 2. Update your .env

Create or edit `.env` in the repo root with **local** URLs:

```env
# Local Postgres (from docker-compose.local.yml)
DATABASE_URL=postgresql://steampipe:steampipe@localhost:5432/steampipe

# Local Redis
REDIS_URL=redis://localhost:6379/0

# Optional: local snapshots (no S3 needed for dev)
USE_LOCAL_STORAGE=true
LOCAL_STORAGE_PATH=./local/snapshots
```

### 3. Apply migrations (two repos, shared Postgres)

**Stage 1 — this repo (public schema):**

```bash
./scripts/init_db.sh
```

Applies:

- **001** – tenants, users, api_keys, cloud_accounts, queries, schedules, execution_jobs, execution_results
- **002** – execution_batches, batch_id, content_hash, indexes
- **007** – framework scan schedules on `query_schedules` (T-030)

**Stage 2 — [cloud-compliance-engine](https://github.com/YOUR_ORG/cloud-compliance-engine) sibling repo (`compliance` schema):**

```bash
cd ../cloud-compliance-engine
alembic upgrade head
python -m app.scripts.seed_catalog
```

Compliance migrations use table `alembic_version_compliance` (separate from Stage 1 `alembic_version`).

### 4. Seed Stage 1 query catalog (optional)

```bash
python scripts/setup_compliance.py
```

Loads `data/queries.json` into `public.queries` (CIS compliance queries for scans).

### 5. (Optional) Seed dummy data for main app

For tenants, users, cloud accounts, queries (used by execution platform):

```bash
python scripts/seed_dummy_data.py
```

### 6. Run the app

**Stage 1 — execution platform (this repo):**

```bash
./scripts/run_api.sh      # Terminal 1 → :8000
./scripts/run_worker.sh   # Terminal 2
./scripts/run_scheduler.sh # Terminal 3
```

**Stage 2 — compliance (sibling repo):**

```bash
cd ../cloud-compliance-engine
docker compose up -d   # compliance-api :8001 + compliance-worker
```

E2E smoke: `python scripts/smoke_e2e_scan.py` (from steampipe repo).

---

## Schema overview

| Schema    | Owner repo | Tables |
|-----------|------------|--------|
| **public** | steampipe | tenants, users, cloud_accounts, queries, query_schedules, execution_batches, execution_jobs, execution_results |
| **compliance** | cloud-compliance-engine | controls, scan_runs, snapshots, control_results, control_state, … |

Postgres holds all data; Redis: Stage 1 job queue + `steampipe:job_completed` events for compliance worker.

---

## Reusing existing Railway URLs

If you provision **new** Postgres and Redis on Railway (or another provider), update `.env` with the new URLs and run steps 3–6 above. Migrations are idempotent; a fresh DB will get all tables.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `could not connect to server` | Ensure `docker compose -f docker-compose.local.yml up -d` is running; wait for health checks. |
| `relation "tenants" does not exist` | Run `./scripts/init_db.sh` first. |
| Empty `GET /v1/controls` on :8001 | Run `seed_catalog` in **cloud-compliance-engine** repo. |
| Redis connection refused | Ensure Redis container is running: `docker compose -f docker-compose.local.yml ps`. |
| Alembic "duplicate key" | DB already has schema; you're reapplying. Use `alembic downgrade base` then `alembic upgrade head` only if you truly want a full reset. |
