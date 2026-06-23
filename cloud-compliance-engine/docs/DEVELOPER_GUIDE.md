# Developer Guide

How the code is organized and how to extend it.

---

## 1. Entry points

| Entry | File | When it runs |
|-------|------|--------------|
| Compliance worker | `app/workers/compliance_worker.py` | Always (background) |
| Compliance API | `app/main.py` | HTTP requests |
| Seed catalog | `app/scripts/seed_catalog.py` | Setup / after YAML changes |

---

## 2. Pipeline (core logic)

### `process_job_completed` — start here

**File:** `app/services/pipeline/process_job.py`

Called for every Redis `job_completed` event:

```
filter category == compliance
  → get_registry(db)           # rules from public.queries
  → get_or_create_scan_run()   # compliance.scan_runs
  → extract_snapshot_to_db()   # Bronze → Silver
  → evaluate_snapshot()        # Silver → Gold
  → record_control_evaluated()
  → maybe_finalize_scan_run()  # score when batch complete
```

### `extract_snapshot_to_db`

**File:** `app/services/extract.py`

- Resolves local path (`local/snapshots/...` vs Docker mount)
- Parses `metadata` + `rows` from JSON
- Inserts `compliance.snapshots` (with `batch_id`, `control_ref`, …)
- Inserts `execution_snapshot_rows` (idempotent on `snapshot_id + record_hash`)

### `evaluate_snapshot`

**File:** `app/services/evaluate.py`

- Loads rule by `control_ref` from `RuleRegistry`
- Joins `compliance.controls` for title, severity, remediation
- `apply_pass_rule(pass_rule, row_count)` → PASS/FAIL
- Writes `evaluation_runs`, `control_results`, `control_evidence_resources`
- Upserts `control_state`

### `scan_run` lifecycle

**File:** `app/services/pipeline/scan_run.py`

- `total_controls` from `execution_batches.total_jobs` (35 for CIS scan)
- Increments counters per control
- When `evaluated_controls >= total_controls`: `status=completed`, `score_pct = pass/evaluated * 100`

---

## 3. Rule engine

| File | Responsibility |
|------|----------------|
| `rule_engine/catalog.py` | Parse `data/queries.json` compliance entries |
| `rule_engine/registry.py` | `get_registry(db)` — DB first, file fallback |
| `rule_engine/engine.py` | `apply_pass_rule`, `build_evidence_entries` |

**Adding a pass rule:**

1. Add case in `engine.py` → `apply_pass_rule`
2. Set `pass_rule` in query `extra_metadata`
3. Re-run `apply_queries_document.py`

---

## 4. Models

**File:** `app/models/compliance.py`

Key models:

- `ScanRun` — customer scan unit (`batch_id`)
- `Snapshot` / `ExecutionSnapshotRow` — Silver
- `ControlResult` / `ControlEvidenceResource` — Gold
- `ControlState` — latest cache for dashboard

Migrations: repo root `alembic/versions/003_*.py`, `005_compliance_scan_runs.py`

---

## 5. API layer

Routers in `app/api/v1/`:

| Router | Customer use |
|--------|--------------|
| `scan_runs.py` | Primary — scan list, matrix, backfill |
| `control_results.py` | Evidence |
| `control_status.py` | Latest posture |
| `controls.py` | Catalog listing |
| `evaluation_runs.py` | Manual one-off evaluate |
| `snapshots.py` | Ingest without evaluate |
| `simulate.py` | Test rules without DB writes |

**Tenant header:** All routes expect `X-Tenant-Id: <uuid>` (or `DEFAULT_TENANT_ID` in `.env`).

**DB commit:** `app/api/deps.py` `get_db()` commits on success.

---

## 6. Adding a new automated control

1. **`data/queries.json`** — add query with:
   ```json
   "extra_metadata": {
     "category": "compliance",
     "framework_id": "cis_aws_v6",
     "control_id": "X.Y",
     "control_ref": "my-control-ref",
     "pass_rule": "zero_rows",
     "required_columns": ["name", "region"]
   }
   ```

2. **`config/cis_v6_controls.yaml`** — add control block with `control_ref`, title, severity, remediation

3. **Apply:**
   ```bash
   python scripts/setup_compliance.py
   ```

4. **Verify:** Run scan or `POST /v1/scan-runs/{batch_id}/process`

---

## 7. Adding a new framework (future)

See [ADDING_FRAMEWORKS.md](ADDING_FRAMEWORKS.md). Summary:

1. Add entry to `config/catalog.yaml`
2. Add controls YAML + compliance queries in `data/queries.json` with new `framework_id`
3. Run seed + apply queries

---

## 8. Testing

```bash
# From repo root
PYTHONPATH=cloud-compliance-engine python -m pytest cloud-compliance-engine/tests -v
```

Or: `make -C cloud-compliance-engine test`

---

## 9. Debugging checklist

| Symptom | Check |
|---------|-------|
| No scan_runs after scan | Is `compliance-worker` running? Redis queue depth? |
| processed=0 on backfill | Snapshot path resolution; volume mount `./local/snapshots` |
| Wrong PASS/FAIL | Row count in Bronze JSON; `pass_rule` in metadata |
| Empty control matrix | `X-Tenant-Id` matches batch tenant |
| Rules not found | Run `setup_compliance.py`; check `public.queries` compliance rows |

---

## 10. Code map (quick reference)

```
Event in  → compliance_worker.py
Orchestrate → pipeline/process_job.py
Bronze→Silver → extract.py
Silver→Gold   → evaluate.py
Rules         → rule_engine/*
Scan score    → pipeline/scan_run.py
Customer API  → api/v1/scan_runs.py
```
