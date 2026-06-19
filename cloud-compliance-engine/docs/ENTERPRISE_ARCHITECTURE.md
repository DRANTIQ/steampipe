# Enterprise Architecture Additions

Checklist of architecture-level improvements for audit-grade, multi-tenant compliance platform. See **PROMPT.md** for full schema and implementation details.

---

## 1. Evaluation lifecycle — evaluation_runs table

**Problem:** execution_job_id is reused everywhere; lifecycle state is implicit.

**Solution:** Dedicated `evaluation_runs` table:

| Field | Type |
|-------|------|
| id | UUID |
| execution_job_id | UUID |
| tenant_id | UUID |
| account_id | UUID |
| framework | TEXT |
| framework_version | TEXT |
| rule_set_version | TEXT |
| snapshot_hash | VARCHAR(64) |
| started_at | TIMESTAMPTZ |
| completed_at | TIMESTAMPTZ |
| status | ENUM (running, completed, failed) |

**Benefits:** Audit trail, partial failure handling, observability, retry, backfill. Make lifecycle explicit.

---

## 2. Deterministic evaluation strategy

**Goal:** Same snapshot + same rule hash = same result (audit defense).

- **Canonicalize JSON before hashing:** sort keys recursively; normalize null vs missing.
- **Freeze rule definitions during evaluation:** copy rule JSON into evaluation_run context; hash that.
- **snapshot_hash:** compute on canonicalized snapshot content. Same file → same hash every time.

---

## 3. Soft delete / historical integrity

**Rule:** Never hard delete:

- control_results  
- execution_snapshot_rows  
- evaluation_runs  

**Approach:** Add `archived_at` (set timestamp when archiving) or use time-based retention policies. Auditors require traceability.

---

## 4. Row-level security (multi-tenant SaaS)

**Approach:** Enable PostgreSQL RLS on all tenant-scoped tables:

```sql
ALTER TABLE control_results ENABLE ROW LEVEL SECURITY;
-- Policy: tenant_id = current_setting('app.current_tenant_id')::UUID
```

Apply to: control_results, execution_snapshot_rows, evaluation_runs, compliance_summary, control_state. Prevents cross-tenant leaks; critical for SOC2.

---

## 5. Evidence storage optimization

- **Strategy:** Store only required fields in evidence JSONB on control_results. Full raw row stays in execution_snapshot_rows (snapshot table).
- **Optional:** Compress evidence JSONB; or move large evidence to object storage if > X KB and store pointer. Monitor TOAST growth.

---

## 6. Index strategy (scale read patterns)

**Examples:**

- **Dashboards:** (tenant_id, framework, control_id, latest_status) on control_state or mv.
- **Failed controls:**  
  `CREATE INDEX idx_failed_controls ON control_results (tenant_id, framework) WHERE status = 'failed';`  
  Huge speed improvement for "show me failures".

---

## 7. Risk impact multiplier

Beyond severity_weighted_score: add account-level **risk_tier** (e.g. Production / Staging / Dev).

- Multiply severity weight by: Production = 2, Staging = 1, Dev = 0.5 (configurable).
- Use in compliance_summary or risk engine. Risk-aware beyond severity = differentiation.

---

## 8. Continuous compliance mode (optional)

**Snapshot-based today.** Add optional:

- Re-evaluate only controls impacted by changed query_ids.
- Delta-based evaluation to reduce cost at scale. Phase 2.

---

## 9. Control execution metrics — control_metrics table

| Field | Purpose |
|-------|--------|
| control_id | Control identifier |
| avg_eval_time_ms | Identify slow controls |
| last_eval_duration_ms | Last run duration |
| row_count_processed | Capacity planning |

Helps: optimize rule engine, capacity planning, identify slow controls.

---

## 10. SLA monitoring for evaluations

With evaluation_runs:

- Enforce max execution time per tenant (config: max_evaluation_duration_seconds).
- Alert if evaluation run exceeds threshold. Important at enterprise scale.

---

## 11. Partition strategy (two-level)

**Best practice at scale:**

1. **tenant_id** (LIST partition) — avoids single-tenant heavy query impact and global index bloat.
2. **run_at** (RANGE, e.g. monthly) — time-series.

Implement in Phase 2 after MVP.

---

## 12. Control status history API optimization

- **Dashboards:** Use **control_state** and **mv_latest_control_status** for latest status only. Do **not** query full control_results history for default view.
- **History:** Expose via separate API (e.g. GET /control_results?history=true). Keep "current state" fast.

---

## 13. Tamper protection (hash chain)

**Audit-grade:** Append-only integrity. Few vendors implement this.

- **evaluation_hash** on evaluation_runs:  
  `SHA256(previous_evaluation_hash || current_snapshot_hash || rule_definition_hash)`  
- Chain per tenant/account; first row uses seed (e.g. SHA256('genesis')). Store previous_evaluation_hash; verify on read or audit job.

---

## 14. Multi-cloud extensibility

**Approach:** Add **cloud_provider** column (aws / azure / gcp) on:

- evaluation_runs  
- control_results  
- controls  
- compliance_summary  

Later: Azure CIS, GCP CIS without schema refactor. Future-proof now.

---

## 15. Control scoping

Allow controls to have scope for regional / resource-group reporting:

| scope_type | scope_value |
|------------|-------------|
| account | * |
| region | us-east-1 |
| resource_group | rg-* |

Add to controls table. Enables scoped evaluation and regional compliance reporting.

---

## 16. Control maturity level

Add to controls table: **maturity_level** INT.

- Level 1 (baseline), 2 (advanced), 3 (hardened).  
- Enables tiered compliance programs.

---

## 17. Snapshot metadata table — snapshots

Instead of only execution_snapshot_rows, create:

| Field | Purpose |
|-------|---------|
| id | PK |
| snapshot_hash | Unique |
| execution_job_id | Source |
| row_count | Metadata |
| total_size_bytes | Optional |
| created_at | |

execution_snapshot_rows references **snapshot_id**. Better normalization.

---

## 18. Observability and logging

- **Structured logs:** evaluation_run_id, control_id, duration_ms, row_count, status.
- **Push to:** OpenTelemetry (or structured JSON to log aggregator).  
- When enterprise customer asks for root cause → you're ready.

---

## Most important immediate additions (do first)

1. **evaluation_runs** table  
2. **cloud_provider** column everywhere  
3. **RLS** for tenant isolation  
4. **Canonical JSON hashing** (deterministic evaluation)  
5. **Partial index** on failed controls (`WHERE status = 'failed'`)  

Everything else can be phased (see PROMPT.md §13 Implementation roadmap).

---

## Final assessment

- **Current (with earlier additions):** ~9/10  
- **With evaluation_runs, RLS, hash-chain tamper protection, multi-cloud, partition refinement:**  
  **True enterprise compliance platform architecture (9.5/10).**
