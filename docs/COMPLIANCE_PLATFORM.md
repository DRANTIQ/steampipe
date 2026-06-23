# Compliance Platform (Stage 1 + Stage 2)

Platform-level overview linking Steampipe execution and the Cloud Compliance Engine.

**Full compliance docs:** [cloud-compliance-engine/docs/README.md](../cloud-compliance-engine/docs/README.md)

---

## Two stages, one product

| Stage | Folder | Port | Job |
|-------|--------|------|-----|
| **1 — Collection** | `src/` | 8000 | Run Steampipe, write Bronze snapshots |
| **2 — Compliance** | `cloud-compliance-engine/` | 8001 | Evaluate PASS/FAIL, serve scan scores |

Connected by:

- Redis: `steampipe:job_completed`
- Postgres: `public.*` + `compliance.*`
- Files: `./local/snapshots/.../{batch_id}/{job_id}/result.json`

---

## Customer journey

```
Connect AWS → Run CIS v6 scan → View score (77%) → Drill into 8 failures → Fix → Re-scan
```

**Product unit:** one scan = one `batch_id` = one `compliance.scan_runs` row.

---

## Single catalog

All Steampipe SQL and evaluation rules: **[data/queries.json](data/queries.json)**

Control titles/severity: **[cloud-compliance-engine/config/cis_v6_controls.yaml](../cloud-compliance-engine/config/cis_v6_controls.yaml)**

Setup: **`python scripts/setup_compliance.py`**

---

## Quick commands

```powershell
# Setup (once)
docker compose -f docker-compose.remote.yml run --rm -v "${PWD}:/app" -e PYTHONPATH=/app/cloud-compliance-engine:/app api python scripts/setup_compliance.py

# Run stack
docker compose -f docker-compose.remote.yml up -d --scale worker=4 api worker compliance-api compliance-worker

# Scan
curl -X POST http://localhost:8000/api/v1/executions/scan ...

# Results
curl http://localhost:8001/v1/scan-runs/BATCH_ID -H "X-Tenant-Id: ..."
```

---

## Documentation map

| Topic | Document |
|-------|----------|
| **Task tracker (checklist)** | [TASK_TRACKER.md](TASK_TRACKER.md) |
| **Phase 1 — stability & bronze pinning** | [PHASE1.md](PHASE1.md) |
| **Prioritized task list** | [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) |
| Compliance runbook | [cloud-compliance-engine/RUNBOOK.md](../cloud-compliance-engine/RUNBOOK.md) |
| Architecture | [cloud-compliance-engine/docs/ARCHITECTURE.md](../cloud-compliance-engine/docs/ARCHITECTURE.md) |
| Folder layout | [cloud-compliance-engine/docs/FOLDER_STRUCTURE.md](../cloud-compliance-engine/docs/FOLDER_STRUCTURE.md) |
| Developer guide | [cloud-compliance-engine/docs/DEVELOPER_GUIDE.md](../cloud-compliance-engine/docs/DEVELOPER_GUIDE.md) |
| API | [cloud-compliance-engine/docs/API.md](../cloud-compliance-engine/docs/API.md) |
| CIS scan (Stage 1) | [CIS_SCAN_RUNBOOK.md](CIS_SCAN_RUNBOOK.md) |
| Licensing | [QUERIES_AND_COMPLIANCE_DESIGN.md](QUERIES_AND_COMPLIANCE_DESIGN.md) |
| Worker scaling | [SCALING_ROADMAP.md](SCALING_ROADMAP.md) |

---

## Commercial scope (v1)

- Framework: **CIS AWS Foundations v6.0.0** (`cis_aws_v6`)
- ~35 automated technical controls
- Claim: **aligned with** CIS v6 automated subset — not full CIS certification
