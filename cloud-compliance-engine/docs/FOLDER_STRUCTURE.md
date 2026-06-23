# Folder Structure

Clean layout for the Cloud Compliance Engine. Only **runtime** and **config** paths are required to run the product.

---

## Tree

```
steampipe/                              # Repo root
├── data/
│   └── queries.json                    # SINGLE SOURCE: SQL + pass_rule metadata
├── scripts/
│   ├── setup_compliance.py             # migrate + apply queries + seed catalog
│   └── apply_queries_document.py       # Stage 1: queries.json → public.queries
├── alembic/versions/
│   ├── 003_compliance_schema.py
│   ├── 004_compliance_provider_category.py
│   └── 005_compliance_scan_runs.py
│
└── cloud-compliance-engine/
    ├── README.md                       # Entry point + quick start
    ├── RUNBOOK.md                      # Operations guide
    │
    ├── app/                            # === RUNTIME ===
    │   ├── main.py                     # FastAPI app (port 8001)
    │   ├── config.py                   # Env: DATABASE_URL, COMPLIANCE_QUEUE_KEY
    │   ├── database.py                 # SQLAlchemy session + RLS helper
    │   │
    │   ├── workers/
    │   │   └── compliance_worker.py    # Redis BLPOP → process_job_completed
    │   │
    │   ├── services/
    │   │   ├── extract.py              # Bronze JSON → compliance.snapshots + rows
    │   │   ├── evaluate.py             # Rows + rules → control_results
    │   │   ├── hash_utils.py           # Deterministic hashes for audit
    │   │   ├── rule_registry.py        # Back-compat re-export
    │   │   ├── pipeline/
    │   │   │   ├── process_job.py      # Orchestrator: extract → evaluate → scan
    │   │   │   └── scan_run.py         # Scan lifecycle, score_pct
    │   │   └── rule_engine/
    │   │       ├── catalog.py          # Parse rules from data/queries.json
    │   │       ├── registry.py         # Load rules from DB or file
    │   │       └── engine.py           # pass_rule + evidence building
    │   │
    │   ├── api/
    │   │   ├── deps.py                 # DB session, X-Tenant-Id, commit
    │   │   └── v1/
    │   │       ├── scan_runs.py        # Customer: scan list, matrix, backfill
    │   │       ├── control_results.py  # Customer: evidence drill-down
    │   │       ├── control_status.py   # Latest posture per control
    │   │       ├── controls.py         # Control catalog from DB
    │   │       ├── evaluation_runs.py  # Manual single-control evaluate
    │   │       ├── snapshots.py        # Manual ingest only
    │   │       └── simulate.py         # Dry-run, no persist
    │   │
    │   ├── models/
    │   │   └── compliance.py           # scan_runs, snapshots, control_results, …
    │   ├── schemas/
    │   │   └── common.py               # Pydantic API models
    │   └── scripts/
    │       └── seed_catalog.py         # YAML controls → compliance.controls
    │
    ├── config/                         # === CONFIG ===
    │   ├── catalog.yaml                # Frameworks to seed (cis_aws_v6)
    │   ├── cis_v6_controls.yaml        # Control titles, severity, remediation
    │   └── cis_v6_controls.example.yaml
    │
    ├── docs/                           # === DOCUMENTATION ===
    │   ├── README.md                   # Doc index
    │   ├── ARCHITECTURE.md
    │   ├── DEVELOPER_GUIDE.md
    │   ├── API.md
    │   ├── CATALOG.md
    │   ├── FOLDER_STRUCTURE.md         # (this file)
    │   ├── ADDING_FRAMEWORKS.md
    │   ├── CIS_V6_REFERENCE.md
    │   └── archive/                    # Legacy specs (ignore)
    │
    ├── reference/                      # === NON-RUNTIME ===
    │   └── cis_v6.pp                   # Powerpipe reference only
    │
    └── tests/
        ├── unit/
        └── fixtures/
```

---

## What runs where

| Process | Command | Reads |
|---------|---------|-------|
| Compliance API | `uvicorn app.main:app --port 8001` | Postgres `compliance.*` |
| Compliance worker | `python -m app.workers.compliance_worker` | Redis + snapshots + Postgres |
| Seed | `python -m app.scripts.seed_catalog` | `config/*.yaml`, `data/queries.json` |

Stage 1 (separate service in repo root `src/`):

| Process | Role |
|---------|------|
| `api` :8000 | Create scans, enqueue jobs |
| `worker` | Steampipe → Bronze snapshots → Redis events |

---

## What we removed (cleanup)

| Removed | Reason |
|---------|--------|
| `queries/cis_v6_queries.json` | Duplicate of `data/queries.json` |
| `docs/queries.json` | Stale copy |
| `docs/cis_v6_controls.yaml` | Duplicate of `config/cis_v6_controls.yaml` |
| Root `IMPLEMENTATION_PROMPT.md`, etc. | Moved to `docs/archive/` |

---

## Environment variables

| Variable | Default | Used by |
|----------|---------|---------|
| `DATABASE_URL` | (from `.env`) | All |
| `REDIS_URL` | (from `.env`) | Worker |
| `COMPLIANCE_QUEUE_KEY` | `steampipe:job_completed` | Worker |
| `USE_LOCAL_STORAGE` | `true` (dev) | Extract (read snapshots) |
| `LOCAL_STORAGE_PATH` | `./local/snapshots` | Extract |
