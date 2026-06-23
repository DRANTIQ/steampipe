# Architecture: Extract First vs Engine-Only — Best Mapping

**Question:** What is best — **extract the data first, then apply rules**, or have the **engine do extraction into DB** in one go? Think like an architect.

---

## 1. Two main options

| Approach | Extract | Evaluate | Where data lives |
|----------|--------|----------|-------------------|
| **A. Extract first, then rules** | Separate step: S3 → DB (generic table) | Engine reads from DB, applies pass_rule, writes control_results | Snapshot rows in DB; engine is stateless over that data |
| **B. Engine does both** | Engine reads S3, evaluates in memory, writes only control_results (+ optional compliance_summary) | Same process | No persistent copy of snapshot rows; only control_results |

There is a **third**, hybrid pattern that is usually the best trade-off:

| Approach | Extract | Evaluate | Where data lives |
|----------|--------|----------|-------------------|
| **C. Extract as first phase of engine** | **Phase 1:** Load S3 JSON → write to `snapshot_data` (or `execution_snapshot_rows`) table | **Phase 2:** Read from that table, apply rules → control_results; **Phase 3:** Aggregate → compliance_summary | One pipeline; snapshot rows in DB; re-run rules without re-reading S3 |

---

## 2. Recommended: Extract first (then apply rules)

**Best mapping from an architect’s perspective:**

```
S3 snapshot (JSON)
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1 — EXTRACT (into DB)                                      │
│  • One table: execution_snapshot_rows (or snapshot_data)           │
│  • Rows: execution_job_id, query_id, tenant_id, account_id,        │
│          run_at, row_index, row_data (JSONB)                       │
│  • Idempotent: upsert by (execution_job_id, row_index)             │
│  • Purpose: "What did we actually see?" — single source of truth   │
└──────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2 — APPLY RULES (compliance engine)                         │
│  • Read from execution_snapshot_rows (filter by execution_job_id   │
│    + query metadata: framework, control_ref, pass_rule)            │
│  • Evaluate: e.g. zero_rows → pass if count = 0 else fail          │
│  • Build evidence from row_data + required_columns                 │
│  • Write: control_results (+ optional compliance_summary)          │
│  • Idempotent: upsert by (execution_job_id, framework, control_ref)│
└──────────────────────────────────────────────────────────────────┘
       │
       ▼
  control_results  →  compliance_summary  →  Risk Engine  →  API
```

**Why this is better:**

1. **Single source of truth in DB**  
   “What we evaluated” lives in `execution_snapshot_rows`. You can re-run the engine (e.g. new rules or bug fix) without touching S3 again.

2. **Audit and debugging**  
   Support and auditors can inspect raw snapshot rows for any execution. Evidence in control_results can reference `row_index` or keys in `row_data`.

3. **Clear separation of concerns**  
   - **Extract:** “Get snapshot from S3 into DB in a generic, queryable shape.”  
   - **Rules:** “From that shape, compute pass/fail and evidence.”  
   You can change rules or add frameworks without changing how you store raw data.

4. **Backfill and replay**  
   Backfill = run extract for old executions (if you have snapshot_path), then run engine. No need to re-run Steampipe.

5. **Cost and performance**  
   S3 read once per execution; all later steps (and re-runs) read from DB. You can also archive or drop old snapshot rows by policy (e.g. after 90 days) and keep only control_results if needed.

---

## 3. Schema for “extract” (recommended)

**Option 3a — Generic (one table, flexible):**

```sql
-- execution_snapshot_rows: one row per snapshot row, per execution
CREATE TABLE execution_snapshot_rows (
  id                UUID PRIMARY KEY,
  execution_job_id  UUID NOT NULL,   -- links to execution platform
  tenant_id         UUID NOT NULL,
  account_id        UUID NOT NULL,
  query_id          UUID NOT NULL,
  run_at            TIMESTAMPTZ NOT NULL,
  row_index         INT NOT NULL,   -- 0, 1, 2, ... within that execution
  row_data          JSONB NOT NULL, -- the Steampipe row as JSON
  UNIQUE(execution_job_id, row_index)
);

CREATE INDEX idx_snapshot_rows_exec ON execution_snapshot_rows(execution_job_id);
CREATE INDEX idx_snapshot_rows_tenant_run ON execution_snapshot_rows(tenant_id, run_at);
```

- **Extract step:** For each execution, read S3 JSON, insert one row per element in `rows` (or equivalent) with `row_data = that row`.
- **Engine:** For a given `execution_job_id`, load `row_data` (and optionally only `required_columns`), apply pass_rule, build evidence from `row_data`, write control_results.

**Option 3b — Normalized (one table per resource type):**

- e.g. `snapshot_s3_buckets`, `snapshot_rds_instances` with columns matching the query.
- Pros: SQL-friendly, strong typing. Cons: schema change per query type; more tables. Use only if you want to run heavy SQL analytics on raw snapshot data; for compliance evaluation alone, **3a is enough**.

**Recommendation:** Start with **3a (generic)**. Add 3b later only if you need it for reporting or risk logic that queries raw resource attributes directly.

---

## 4. Where “extract” lives

- **In the Compliance Engine repo (recommended):**  
  Extract is **Phase 1** of the same service. Trigger: “execution X finished; snapshot at path P.” Engine: (1) load P from S3 → write `execution_snapshot_rows`, (2) evaluate from that table → write control_results, (3) update compliance_summary.  
  One codebase, one deployment; clear pipeline.

- **In the Execution platform (Steampipe) repo:**  
  After writing the snapshot to S3, the execution platform also writes the same rows to a shared DB (`execution_snapshot_rows`). Compliance Engine only runs Phase 2–3 (read from DB, evaluate, write control_results).  
  Pros: Snapshot is in DB as soon as the job finishes. Cons: Execution platform must know about the “extract” schema and DB; tighter coupling.

**Architect recommendation:** Keep **extract inside the Compliance Engine** as Phase 1. Execution platform only publishes “job X done; snapshot_path = P; query_id = Q.” Engine owns “load P → DB → evaluate → control_results.” Loose coupling; one place to change extract or rules.

---

## 5. End-to-end mapping (summary)

| Step | Owner | Input | Output |
|------|--------|--------|--------|
| 1. Extract | Compliance Engine | S3 path (from execution platform), execution_job_id, tenant_id, account_id, query_id, run_at | `execution_snapshot_rows` |
| 2. Apply rules | Compliance Engine | `execution_snapshot_rows` + query metadata (framework, control_ref, pass_rule, required_columns) | `control_results` |
| 3. Summarise | Compliance Engine | `control_results` | `compliance_summary` |
| 4. Risk | Risk Engine | `control_results` / `compliance_summary` | risk scores / findings |
| 5. API / Dashboard | API layer | `control_results`, `compliance_summary`, risk | REST / UI |

**Best practice:** Extract first into a generic DB table, then apply rules from that table. That gives you a single source of truth, re-runs without S3, clear separation, and a simple mapping from S3 → DB → rules → control_results → compliance_summary → Risk → API.
