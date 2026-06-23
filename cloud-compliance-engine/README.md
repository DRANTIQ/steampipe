# Cloud Compliance Engine

Evaluates CIS AWS v6 scans from the Steampipe execution platform and exposes customer-facing PASS/FAIL results.

**Documentation:** [docs/README.md](docs/README.md)

---

## Quick start

```powershell
# From repo root (once)
docker compose -f docker-compose.remote.yml run --rm -v "${PWD}:/app" -e PYTHONPATH=/app/cloud-compliance-engine:/app api python scripts/setup_compliance.py

# Start stack
docker compose -f docker-compose.remote.yml up -d --scale worker=4 api worker compliance-api compliance-worker
```

| Service | URL | Role |
|---------|-----|------|
| Stage 1 API | http://localhost:8000 | Trigger CIS scans |
| Compliance API | http://localhost:8001/docs | View scan scores + controls |
| Compliance worker | (background) | Auto evaluate on job complete |

---

## What it does

```
Scan (Stage 1)  →  Bronze JSON snapshots
               →  compliance-worker (Redis events)
               →  Extract + Evaluate (Postgres)
               →  scan_runs + control_results (API for UI)
```

---

## Folder layout

```
cloud-compliance-engine/
├── app/                    # Runtime code
│   ├── workers/            # compliance_worker.py
│   ├── services/           # extract, evaluate, pipeline, rule_engine
│   ├── api/v1/             # REST endpoints
│   ├── models/             # compliance schema ORM
│   └── scripts/            # seed_catalog.py
├── config/                 # catalog.yaml, cis_v6_controls.yaml
├── docs/                   # All documentation
├── reference/              # Non-runtime reference (Powerpipe)
└── tests/
```

Full map: [docs/FOLDER_STRUCTURE.md](docs/FOLDER_STRUCTURE.md)

---

## Single catalog

| Content | Location |
|---------|----------|
| Steampipe SQL + pass_rule metadata | [`../data/queries.json`](../data/queries.json) |
| Control titles, severity, remediation | [`config/cis_v6_controls.yaml`](config/cis_v6_controls.yaml) |

No duplicate query files inside this folder.

---

## Key commands

```powershell
# Backfill an existing scan batch
curl.exe -X POST "http://localhost:8001/v1/scan-runs/BATCH_ID/process" -H "X-Tenant-Id: TENANT_UUID"

# View scan score
curl.exe "http://localhost:8001/v1/scan-runs/BATCH_ID" -H "X-Tenant-Id: TENANT_UUID"

# Control matrix
curl.exe "http://localhost:8001/v1/scan-runs/BATCH_ID/controls" -H "X-Tenant-Id: TENANT_UUID"
```

See [RUNBOOK.md](RUNBOOK.md) for the full operational guide.
