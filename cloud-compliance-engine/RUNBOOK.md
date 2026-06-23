# Runbook — Cloud Compliance Engine

Operational guide: setup, run scans, view results, troubleshoot.

**Doc index:** [docs/README.md](docs/README.md)

---

## Prerequisites

- Docker Compose remote stack (Supabase Postgres + Upstash Redis)
- `.env` with `DATABASE_URL`, `REDIS_URL`, `USE_LOCAL_STORAGE=true`, `LOCAL_STORAGE_PATH=./local/snapshots`
- Stage 1 tenant + AWS account seeded

---

## One-time setup

From repo root:

```powershell
docker compose -f docker-compose.remote.yml run --rm -v "${PWD}:/app" -e PYTHONPATH=/app/cloud-compliance-engine:/app api python scripts/setup_compliance.py
```

This runs:

1. `alembic upgrade head` — creates `compliance` schema + `scan_runs`
2. `apply_queries_document.py` — `data/queries.json` → `public.queries`
3. `seed_catalog` — `cis_v6_controls.yaml` → `compliance.controls`

---

## Start services

```powershell
docker compose -f docker-compose.remote.yml build api worker compliance-api compliance-worker
docker compose -f docker-compose.remote.yml up -d --scale worker=4 api worker compliance-api compliance-worker
```

| Service | Port | Health |
|---------|------|--------|
| Stage 1 API | 8000 | http://localhost:8000/health |
| Compliance API | 8001 | http://localhost:8001/health |
| Compliance worker | — | `docker logs steampipe-compliance-worker-1` |

---

## Run a CIS scan (full E2E)

### 1. Trigger scan (Stage 1)

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/executions/scan" `
  -H "Content-Type: application/json" `
  -d "{\"tenant_id\":\"YOUR_TENANT_UUID\",\"account_id\":\"YOUR_ACCOUNT_UUID\",\"framework_id\":\"cis_aws_v6\",\"category\":\"compliance\"}"
```

Note the `batch_id` in the response.

### 2. Wait (~2 min)

Worker logs: `Account session: batch=... claimed 35 jobs`  
Compliance worker logs: `Processed job=... control=... status=PASS|FAIL`

### 3. View results (Stage 2)

```powershell
curl.exe "http://localhost:8001/v1/scan-runs/BATCH_ID" -H "X-Tenant-Id: YOUR_TENANT_UUID"
curl.exe "http://localhost:8001/v1/scan-runs/BATCH_ID/controls" -H "X-Tenant-Id: YOUR_TENANT_UUID"
```

---

## Backfill existing batch

If snapshots exist but compliance was not running:

```powershell
curl.exe -X POST "http://localhost:8001/v1/scan-runs/BATCH_ID/process" -H "X-Tenant-Id: YOUR_TENANT_UUID"
```

---

## Update query catalog

After editing `data/queries.json`:

```powershell
docker compose -f docker-compose.remote.yml run --rm -v "${PWD}:/app" api python scripts/apply_queries_document.py
docker compose -f docker-compose.remote.yml run --rm -v "${PWD}:/app" -e PYTHONPATH=/app/cloud-compliance-engine:/app api python -m app.scripts.seed_catalog
```

Or run full setup script again.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `scan_runs` empty after scan | Start `compliance-worker`; check Redis `steampipe:job_completed` |
| Backfill `processed: 0` | Rebuild `compliance-api`; check snapshot paths under `./local/snapshots` |
| Wrong PASS/FAIL | Rows in JSON = violations; `zero_rows` means 0 rows = PASS |
| 404 on scan-runs | Wrong `X-Tenant-Id`; run `/process` first |
| Stale SQL in scans | Apply queries with `-v "${PWD}:/app"` mount |

---

## Related

- Stage 1 CIS scan: [../docs/CIS_SCAN_RUNBOOK.md](../docs/CIS_SCAN_RUNBOOK.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- API: [docs/API.md](docs/API.md)
