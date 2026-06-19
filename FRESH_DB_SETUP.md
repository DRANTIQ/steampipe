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

### 3. Apply all migrations (fresh schema)

```bash
./scripts/init_db.sh
```

This runs `alembic upgrade head`, which applies in order:

- **001** – Initial schema: tenants, users, api_keys, cloud_accounts, queries, schedules, execution_jobs, execution_results
- **002** – Production job engine: execution_batches, batch_id, content_hash, indexes
- **003** – Compliance schema: controls, framework_versions, rule_versions, snapshots, evaluation_runs, execution_snapshot_rows, control_results, control_evidence_resources, control_state, compliance_summary, jobs, control_metrics + RLS
- **004** – Provider/category columns on framework_versions and controls

### 4. Seed compliance catalog (controls + frameworks)

Required for the Cloud Compliance Engine APIs:

```bash
PYTHONPATH=cloud-compliance-engine python -m app.scripts.seed_catalog
```

This loads `config/catalog.yaml` → `compliance.controls` and `compliance.framework_versions` (CIS AWS v6 + 34 automated controls).

### 5. (Optional) Seed dummy data for main app

For tenants, users, cloud accounts, queries (used by execution platform):

```bash
python scripts/seed_dummy_data.py
```

### 6. Run the app

**Option A – Main execution platform (API + worker + scheduler):**

```bash
./scripts/run_api.sh      # Terminal 1
./scripts/run_worker.sh   # Terminal 2
./scripts/run_scheduler.sh # Terminal 3
```

**Option B – Cloud Compliance Engine only:**

```bash
PYTHONPATH=cloud-compliance-engine python -m uvicorn app.main:app --reload --app-dir cloud-compliance-engine --port 8000
```

API docs: http://localhost:8000/docs

---

## Schema overview

| Schema    | Tables |
|-----------|--------|
| **public** | tenants, users, api_keys, cloud_accounts, queries, query_schedules, execution_batches, execution_jobs, execution_results |
| **compliance** | controls, framework_versions, rule_versions, snapshots, evaluation_runs, execution_snapshot_rows, control_results, control_evidence_resources, control_state, compliance_summary, jobs, control_metrics |

Postgres holds all data; Redis is used for the job queue (`steampipe:execution_jobs`) and optionally compliance job completion (`compliance:job_completed`).

---

## Reusing existing Railway URLs

If you provision **new** Postgres and Redis on Railway (or another provider), update `.env` with the new URLs and run steps 3–6 above. Migrations are idempotent; a fresh DB will get all tables.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `could not connect to server` | Ensure `docker compose -f docker-compose.local.yml up -d` is running; wait for health checks. |
| `relation "tenants" does not exist` | Run `./scripts/init_db.sh` first. |
| Empty `GET /v1/controls` | Run `PYTHONPATH=cloud-compliance-engine python -m app.scripts.seed_catalog`. |
| Redis connection refused | Ensure Redis container is running: `docker compose -f docker-compose.local.yml ps`. |
| Alembic "duplicate key" | DB already has schema; you're reapplying. Use `alembic downgrade base` then `alembic upgrade head` only if you truly want a full reset. |
