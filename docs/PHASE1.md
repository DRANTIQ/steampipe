# Phase 1 — Dev stability & data correctness

**Goal:** Trust results; no silent misconfig or stale data.  
**Tracker:** [TASK_TRACKER.md](TASK_TRACKER.md) · **Roadmap:** [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)

---

## Tasks

| ID | Task | Status | How |
|----|------|--------|-----|
| T-010 | Reprocess legacy batches (`rule_metadata` / bronze pinning) | Manual | [§ T-010](#t-010-reprocess-legacy-batches) |
| T-011 | Verify bronze pinning | Manual | [§ T-011](#t-011-verify-bronze-pinning) |
| T-012 | Enrich Redis `job_completed` with `pass_rule` / `required_columns` | Done | `src/services/job_completed_event.py` |
| T-013 | Compliance pytest in CI | Done | `cloud-compliance-engine/.github/workflows/ci.yml` |
| T-014 | Stage 1 smoke script (scan + poll) | Done | `scripts/smoke_e2e_scan.py` |
| T-015 | Link roadmap from platform docs | Done | [COMPLIANCE_PLATFORM.md](COMPLIANCE_PLATFORM.md) |

**Exit criteria:** Reproducible tests; bronze immutability verified; legacy batches show `rule_source=bronze`.

---

## T-010: Reprocess legacy batches

Snapshots created before migration `004` may lack `compliance.snapshots.rule_metadata`. Reprocessing re-extracts Bronze JSON and pins rules at scan time.

### Known batches to reprocess

| Batch ID | Notes |
|----------|-------|
| `beef0081-5617-4ca4-bf6a-5480dd7aeab4` | Earlier good backfill |
| `fcf3c645-3704-4dff-a49b-eced9a6698c3` | Stuck 18/35 (dual worker) |
| `7425e74e-a5b2-4d22-b958-a5559d8c02e4` | Latest (27/8/77.14%) |

### Commands

```powershell
# Compliance repo script
cd C:\Users\devar\OneDrive\Documents\GitHub\cloud-compliance-engine
python scripts/reprocess_batch.py `
  --tenant-id 5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47 `
  --batch-id beef0081-5617-4ca4-bf6a-5480dd7aeab4 `
  --batch-id fcf3c645-3704-4dff-a49b-eced9a6698c3

# Or curl
curl.exe -X POST "http://localhost:8001/v1/scan-runs/BATCH_ID/process" `
  -H "X-Tenant-Id: 5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47"
```

### Verify `rule_metadata` populated

```sql
SELECT id, control_ref, rule_metadata IS NOT NULL AS has_metadata
FROM compliance.snapshots
WHERE metadata->>'batch_id' = 'beef0081-5617-4ca4-bf6a-5480dd7aeab4'
LIMIT 5;
```

### Verify `rule_source=bronze` on results

```sql
SELECT cr.control_id, cr.status, cr.details->>'rule_source' AS rule_source
FROM compliance.control_results cr
JOIN compliance.evaluation_runs er ON er.id = cr.evaluation_run_id
JOIN compliance.scan_runs sr ON sr.id = er.scan_run_id
WHERE sr.batch_id = 'beef0081-5617-4ca4-bf6a-5480dd7aeab4'
LIMIT 10;
```

Expect `rule_source` = `bronze` after reprocess.

---

## T-011: Verify bronze pinning

Proves old scans are immutable when live catalog rules change.

### Steps

1. **Pick a control** on a completed batch (e.g. `iam-root-mfa` on `7425e74e-...`).
2. **Record current result:**
   ```powershell
   curl.exe "http://localhost:8001/v1/scan-runs/7425e74e-a5b2-4d22-b958-a5559d8c02e4/controls" `
     -H "X-Tenant-Id: 5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47"
   ```
3. **Change live rule** in `public.queries.extra_metadata` for that control (e.g. flip `pass_rule` or tweak SQL). Apply:
   ```powershell
   cd steampipe
   python scripts/apply_queries_document.py
   ```
4. **Re-evaluate old batch** via `/process` — result for that control should **not** change (uses bronze-pinned `rule_metadata`).
5. **Run a new scan** (`smoke_e2e_scan.py` or `POST /executions/scan`) — new batch should reflect the **updated** rule.

### Pass criteria

| Check | Expected |
|-------|----------|
| Old batch after `/process` | Same PASS/FAIL as before rule change |
| Old batch `rule_source` | `bronze` |
| New batch | Uses updated rule (`live_catalog` or new bronze pin) |

---

## T-012: Redis `job_completed` enrichment

Stage 1 now publishes `pass_rule`, `required_columns`, and `natural_key` from `queries.extra_metadata` alongside Bronze JSON.

- **Builder:** `steampipe/src/services/job_completed_event.py`
- **Publishers:** `execution_worker.py`, `account_session.py`
- **Consumer:** `cloud-compliance-engine/app/services/pipeline/process_job.py` (already reads these fields)

Compliance still works if fields are missing (falls back to Bronze metadata or catalog).

---

## T-013: Compliance pytest in CI

```powershell
cd cloud-compliance-engine
pip install -r requirements.txt
pytest tests/ -v
```

GitHub Actions: `.github/workflows/ci.yml` runs on push/PR to `main`.

---

## T-014: E2E smoke script

```powershell
cd steampipe
python scripts/smoke_e2e_scan.py `
  --tenant-id 5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47 `
  --account-id e0e0075b-310d-4e37-9997-81626fe52580
```

**Requires:** Stage 1 (`:8000`), compliance (`:8001`), workers running, `SNAPSHOT_VOLUME` set in compliance Docker.

Exits `0` when Stage 1 batch completes and compliance shows `status=completed` with 35/35 controls.

---

## T-015: Documentation links

- [COMPLIANCE_PLATFORM.md](COMPLIANCE_PLATFORM.md) — platform overview + doc map
- [TASK_TRACKER.md](TASK_TRACKER.md) — live checklist with completion status
- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) — full phased plan

---

## Test IDs (sandbox)

| Item | Value |
|------|-------|
| Tenant | `5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47` (`drantiq_sandbox`) |
| Account | `e0e0075b-310d-4e37-9997-81626fe52580` |
| AWS account | `387957186076` |
| Framework | `cis_aws_v6` |

---

## Related

- Compliance runbook: `cloud-compliance-engine/RUNBOOK.md`
- Integration contract: `cloud-compliance-engine/contracts/STAGE1_INTEGRATION.md`
