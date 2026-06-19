# Cloud Compliance Engine — Cursor Implementation Prompt

**Purpose:** Build a **production-grade, audit-ready** compliance engine. Two-phase architecture (EXTRACT → RULES), structured evidence, versioned rules & snapshots, severity-weighted scoring, drift detection, framework-agnostic design, event-driven execution, and API-ready layer.

> **Implementation:** Use **[IMPLEMENTATION_PROMPT.md](IMPLEMENTATION_PROMPT.md)** as the single source of truth for building the engine. It consolidates all requirements, schema, API, and step-by-step implementation order. Read IMPLEMENTATION_PROMPT.md first, then this document for feature context.

---

## Included Features & Superpowers

| Feature | Description |
|--------|--------------|
| **Two-phase architecture** | EXTRACT → RULES. Snapshot table separate for replay, audit, drift. |
| **Structured evidence** | Per-resource fields, IDs, actionable summary — not just raw JSON. |
| **Versioned rules & snapshots** | `rule_version`, `snapshot_hash` for audit and historical replay. |
| **Severity-weighted compliance** | Weights per control (Critical / High / Medium / Low) for risk-aware scoring. |
| **Drift detection** | Compare current vs previous control_results; mark status changes. |
| **Framework-agnostic** | Add CIS v5, SOC2, or custom frameworks without rewriting engine. |
| **Time-first & historical** | Query by timestamp or snapshot; support historical compliance views. |
| **Control relationships** | Optional parent/child controls for dashboards and dependency tracking. |
| **Event-driven execution** | Trigger evaluation on new snapshot; support batch or parallel workers. |
| **Pluggable rule engine** | zero_rows, threshold, field_check, regex, custom expressions. |
| **Tenant + account + framework partitioning** | Multi-tenant SaaS dashboards and API. |
| **API-ready layer** | Endpoints for control_results, compliance_summary, evidence inspection. |
| **Tech stack** | Python 3.11+, Postgres, S3, event queue, Alembic, pytest. |
| **Auditability & determinism** | Same snapshot + same rules → same results; canonical JSON hashing; idempotent. |
| **evaluation_runs** | Dedicated evaluation lifecycle table; audit trail, retry, backfill, partial failure handling. |
| **Multi-cloud** | cloud_provider (aws/azure/gcp) on key tables; future Azure CIS, GCP CIS without schema refactor. |
| **RLS** | Row-level security on tenant_id for multi-tenant SaaS (SOC2). |
| **Soft delete** | archived_at; never hard delete control_results, execution_snapshot_rows, evaluation_runs. |
| **Tamper protection** | Optional hash chain (evaluation_hash) on evaluation_runs for append-only integrity. |
| **Control scoping & maturity** | scope_type/scope_value; maturity_level for tiered compliance. |
| **Observability** | Structured logs (evaluation_id, control_id, duration_ms); OpenTelemetry-ready. |

---

## 1. Schema

### 1.0 evaluation_runs (evaluation lifecycle — critical entity)

**Dedicated table for evaluation lifecycle.** Right now execution_job_id is reused everywhere; lifecycle state is implicit. Make it explicit for audit trail, partial failure handling, observability, retry, and backfill.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| execution_job_id | UUID | Links to execution platform |
| tenant_id | UUID | Tenant |
| account_id | UUID | Cloud account |
| cloud_provider | TEXT | aws / azure / gcp (multi-cloud extensibility) |
| framework | TEXT | e.g. "CIS AWS Foundations Benchmark v6.0.0" |
| framework_version | TEXT | e.g. "6.0.0" |
| rule_set_version | TEXT | Version of rule set used |
| snapshot_hash | VARCHAR(64) | Hash of snapshot evaluated |
| evaluation_hash | VARCHAR(64) | Optional: hash chain for tamper protection (see §19) |
| started_at | TIMESTAMPTZ | When evaluation run started |
| completed_at | TIMESTAMPTZ | When completed (null if running or failed) |
| status | ENUM | running / completed / failed |
| archived_at | TIMESTAMPTZ | Null = active; set for soft delete (never hard delete) |

Indexes: (execution_job_id), (tenant_id, status, started_at), (account_id, framework). control_results and execution_snapshot_rows reference evaluation_run_id where useful for traceability.

### 1.0b snapshots (snapshot metadata — normalization)

One row per snapshot; execution_snapshot_rows reference snapshot_id. Better normalization and lifecycle.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| snapshot_hash | VARCHAR(64) | Unique hash of snapshot content |
| execution_job_id | UUID | Source execution |
| row_count | INT | Number of rows |
| total_size_bytes | BIGINT | Optional; size of snapshot |
| created_at | TIMESTAMPTZ | |

execution_snapshot_rows: add snapshot_id UUID FK to snapshots (optional; can still key by execution_job_id).

### 1.1 execution_snapshot_rows (Phase 1 — Extract)

One row per snapshot row, per execution. Single source of truth; enables replay and drift.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| execution_job_id | UUID | Links to execution platform |
| tenant_id | UUID | Tenant |
| account_id | UUID | Cloud account |
| query_id | UUID | Query that produced this snapshot |
| run_at | TIMESTAMPTZ | Execution run time |
| row_index | INT | 0, 1, 2, … within this execution |
| row_data | JSONB | Steampipe row as JSON (full raw row; evidence stores only required fields) |
| snapshot_id | UUID | Optional FK to snapshots table |
| snapshot_hash | VARCHAR(64) | Hash of snapshot content for versioning/audit |
| archived_at | TIMESTAMPTZ | Null = active; soft delete only (auditors require traceability) |

Unique (execution_job_id, row_index). Indexes: (execution_job_id), (tenant_id, run_at). Never hard delete; use archived_at or time-based retention.

### 1.2 control_results (Phase 2 — Evaluation)

One row per (execution, control) with pass/fail, evidence, versioning, drift.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| tenant_id | UUID | Tenant |
| account_id | UUID | Cloud account |
| execution_job_id | UUID | Links to execution platform |
| snapshot_path | TEXT | S3 or local path of snapshot |
| snapshot_hash | VARCHAR(64) | Hash of snapshot used (audit, replay) |
| framework | TEXT | e.g. "CIS AWS Foundations Benchmark v6.0.0" |
| framework_version | TEXT | Optional e.g. "6.0.0" |
| control_id | TEXT | CIS v6 control ID (e.g. 1.1.1) |
| control_ref | TEXT | Human-readable ref (e.g. s3-versioning) |
| parent_control_id | TEXT | Optional; for parent/child control relationships |
| status | ENUM | passed / failed |
| severity | ENUM | Critical / High / Medium / Low (for weighting) |
| rule_version | TEXT | Version of rule definition used |
| evaluated_at | TIMESTAMPTZ | When this evaluation ran |
| run_at | TIMESTAMPTZ | Execution run time (from job) |
| evidence | JSONB | Structured: resource IDs, fields, row_index; actionable |
| summary | TEXT | One-line reason (e.g. "3 buckets with versioning disabled") |
| status_changed | BOOLEAN | True if drift: status differs from previous evaluation |
| previous_status | TEXT | Optional; for drift reporting |

Indexes: (tenant_id, account_id, framework, run_at), (execution_job_id), (control_id, status), (run_at) for time-first queries.

### 1.3 compliance_summary (aggregated)

Rollup by tenant, account, framework, optional control, time window. Severity-weighted. Optionally multiply by account risk_tier (Production/Staging/Dev) for risk-aware score.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| tenant_id | UUID | Tenant |
| account_id | UUID | Nullable if tenant-level only |
| cloud_provider | TEXT | Optional: aws / azure / gcp |
| framework | TEXT | e.g. "CIS AWS Foundations Benchmark v6.0.0" |
| control_id | TEXT | Optional; null = whole framework |
| period_start | TIMESTAMPTZ | Aggregation window start |
| period_end | TIMESTAMPTZ | Aggregation window end |
| total_controls_evaluated | INT | Count of controls run |
| passed_count | INT | Controls passed |
| failed_count | INT | Controls failed |
| pass_percentage | FLOAT | 0–100 |
| severity_weighted_score | FLOAT | Optional; risk-aware score (e.g. Critical=4, High=3, Medium=2, Low=1) |
| last_evaluated_at | TIMESTAMPTZ | Latest evaluation in window |

Indexes: (tenant_id, framework, period_start), (account_id, framework).

### 1.4 controls (control definitions — first-class)

**Critical:** Controls are first-class DB entities, not only config. Enables auditors, remediation in dashboard, risk weighting, multi-framework.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| control_id | TEXT | CIS ID (e.g. 1.1.1). Unique per framework. |
| framework | TEXT | e.g. "CIS AWS Foundations Benchmark v6.0.0" |
| title | TEXT | Official control title |
| description | TEXT | Long description |
| severity | ENUM | Critical / High / Medium / Low |
| remediation | TEXT | Human-readable fix steps (for dashboard) |
| service | TEXT | IAM / S3 / RDS / etc. |
| default_weight | NUMERIC | For severity-weighted score (e.g. Critical=4) |
| enabled | BOOLEAN | Whether this control is evaluated |
| scope_type | TEXT | Optional: account / region / resource_group (control scoping) |
| scope_value | TEXT | Optional: value for scope (e.g. us-east-1) |
| maturity_level | INT | Optional: 1 (baseline), 2 (advanced), 3 (hardened); tiered compliance programs |
| cloud_provider | TEXT | Optional: aws / azure / gcp (multi-cloud) |
| created_at, updated_at | TIMESTAMPTZ | |

Unique (framework, control_id). Index: (framework), (service).

### 1.5 control_state (current state cache)

O(1) lookup for “current compliance”; faster dashboards; real-time risk engine. Maintain instead of recalculating drift every time.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| account_id | UUID | Cloud account |
| control_id | TEXT | Control (references controls.control_id or logical) |
| framework | TEXT | Framework identifier |
| latest_status | ENUM | passed / failed |
| last_run_at | TIMESTAMPTZ | When last evaluated |
| last_snapshot_hash | VARCHAR(64) | Snapshot hash used for this state |
| control_result_id | UUID | FK to control_results (latest) |

Unique (tenant_id, account_id, framework, control_id). Index: (tenant_id, account_id, framework). Refresh on each new control_result for that (account_id, framework, control_id).

### 1.6 control_evidence_resources (evidence normalization)

Two-level evidence: (1) JSONB evidence on control_results (full row); (2) normalized index for search and analytics.

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | PK |
| control_result_id | UUID | FK to control_results |
| resource_id | TEXT | e.g. bucket name, instance id |
| resource_type | TEXT | S3 bucket / RDS instance / IAM user / etc. |
| key_field | TEXT | Primary key field name (e.g. name, id) |
| key_value | TEXT | Value (e.g. my-bucket) |

Indexes: (control_result_id), (resource_type, resource_id) for “show all failed S3 buckets across tenants”, (account_id, control_id) if denormalized. Enables cross-control correlation (Wiz-style).

### 1.7 control_dependencies (dependency graph)

Parent-child controls for rollup, advanced dashboards, risk propagation. Beats Drata on dependency-aware compliance.

| Field | Type | Description |
|-------|------|-------------|
| parent_control_id | TEXT | Parent control (e.g. “IAM configured”) |
| child_control_id | TEXT | Child control (e.g. “2.1.1”) |
| framework | TEXT | Framework |

Unique (framework, parent_control_id, child_control_id). Use for rollup logic and “control group” views.

### 1.8 framework_control_mappings (cross-framework)

Map controls across frameworks: CIS v6 ↔ CIS v5 ↔ SOC2 ↔ in ternal policy. Huge SaaS advantage for “coverage across frameworks”.

| Field | Type | Description |
|-------|------|-------------|
| source_framework | TEXT | e.g. "CIS AWS v6.0.0" |
| source_control_id | TEXT | e.g. "2.1.1" |
| target_framework | TEXT | e.g. "SOC2 CC6.1" |
| target_control_id | TEXT | e.g. "CC6.1-1" |

Index: (source_framework, source_control_id), (target_framework, target_control_id).

### 1.9 rule_versions / framework_versions (audit)

- **rule_versions:** rule_id, version, definition (pass_rule type, params), **rule_definition_hash** (SHA256 of rule JSON), effective_from.
- **framework_versions:** framework, version (e.g. 6.0.0), control set, effective_from.

Use for historical replay and audit: “evaluated with rule hash X and snapshot Y.”

### 1.10 control_results — audit hashing

Add to control_results (if not already):

| Field | Type | Description |
|-------|------|-------------|
| rule_definition_hash | VARCHAR(64) | SHA256 of rule JSON used. Proves “this rule” for audit. |
| snapshot_hash | VARCHAR(64) | Already defined. |
| framework_version | TEXT | e.g. "6.0.0". |

Enterprise audit: “Control evaluated using rule_definition_hash X, snapshot_hash Y, framework_version Z.”

### 1.11 Materialized view — performance

For dashboards, avoid hitting huge control_results. Refresh async (e.g. after new results or on schedule).

```sql
CREATE MATERIALIZED VIEW mv_latest_control_status AS
SELECT DISTINCT ON (account_id, framework, control_id)
  *
FROM control_results
ORDER BY account_id, framework, control_id, run_at DESC;
```

Refresh: `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_control_status;` (requires unique index on the view).

### 1.12 Partitioning (enterprise scale)

**Best practice at scale:** two-level partitioning.

1. **tenant_id** (LIST) — avoids single-tenant heavy query impact and massive global index bloat.
2. **run_at** (RANGE, e.g. monthly) — e.g. control_results_tenant_xyz_2025_01.

Implement in Phase 2. Single-level: partition by run_at first if simpler.

### 1.13 control_metrics (execution metrics per control)

Identify slow controls, optimize rule engine, capacity planning.

| Field | Type | Description |
|-------|------|-------------|
| control_id | TEXT | Control identifier |
| framework | TEXT | Framework |
| avg_eval_time_ms | FLOAT | Average evaluation time (ms) |
| last_eval_duration_ms | FLOAT | Last run duration |
| row_count_processed | BIGINT | Rows processed (last or avg) |
| updated_at | TIMESTAMPTZ | |

Update after each evaluation run (or sample). Index: (control_id, framework).

### 1.14 Row-level security (RLS) and soft delete

- **Multi-tenant SaaS:** Enable PostgreSQL RLS on all tenant-scoped tables (e.g. control_results, execution_snapshot_rows, evaluation_runs, compliance_summary). Policy: `tenant_id = current_setting('app.current_tenant_id')::UUID`. Prevents cross-tenant data leaks; critical for SOC2.
- **Soft delete / historical integrity:** Never hard delete control_results, execution_snapshot_rows, evaluation_runs. Use **archived_at** (set timestamp when archiving) or time-based retention policies. Auditors require traceability.

### 1.15 Tamper protection (hash chain — audit-grade)

Append-only integrity for enterprise compliance. Few vendors implement this.

- **evaluation_hash** on evaluation_runs: `SHA256(previous_evaluation_hash || current_snapshot_hash || rule_definition_hash)`. Chain per tenant or per account; first row uses seed (e.g. SHA256('genesis')).
- Store previous_evaluation_hash on evaluation_runs; verify chain on read or audit job. Enables proof that results were not tampered.

### 1.16 Risk impact multiplier (risk-aware beyond severity)

Account-level risk tier multiplies severity weight for scoring.

- **accounts** (or link from execution platform): risk_tier = Production | Staging | Dev (or similar).
- Multiplier: Production = 2, Staging = 1, Dev = 0.5 (configurable).
- severity_weighted_score in compliance_summary (or risk engine) = sum(severity_weight * risk_tier_multiplier). Differentiates by environment.

### 1.17 Deterministic evaluation strategy (canonical hashing)

Guarantee: **same snapshot + same rule hash = same result.** Critical for audit defense.

- **Canonicalize JSON before hashing:** sort keys recursively; normalize null vs missing (e.g. treat missing key and null consistently).
- **Freeze rule during evaluation:** copy rule JSON into evaluation_run context (or evaluation_runs.rule_snapshot); hash that. Do not rely on live config that might change.
- **snapshot_hash:** compute on canonicalized snapshot content (e.g. sorted keys, normalized nulls). Same file → same hash every time.

### 1.18 Control status history API optimization

- **Dashboards:** Use **control_state** and **mv_latest_control_status** for “latest status only.” Do **not** query full control_results history for default dashboard view.
- **History:** Keep history in control_results; expose via separate API (e.g. GET /control_results?history=true or GET /accounts/:id/control_history). Keeps “current state” fast.

### 1.19 SLA monitoring and continuous compliance

- **SLA:** If evaluation_runs exist, enforce max execution time per tenant (or per run). Alert if evaluation run exceeds threshold. Config: max_evaluation_duration_seconds per tenant.
- **Continuous compliance (optional):** Delta-based evaluation — re-evaluate only controls impacted by changed query_ids; reduces cost at scale. Phase 2.

### 1.20 Observability and logging

- **Structured logs:** evaluation_run_id (or evaluation_id), control_id, duration_ms, row_count, status. Push to OpenTelemetry (or structured JSON to log aggregator). Enables root-cause analysis when enterprise customers ask.

---

## 2. Config

- **Control mapping:** control_ref → CIS v6 control_id (YAML/JSON). Include severity (Critical/High/Medium/Low) per control.
- **Pass_rule definitions:** zero_rows, threshold, field_check, regex, custom expressions. Pluggable registry.
- **Severity weights:** e.g. Critical=4, High=3, Medium=2, Low=1 for severity_weighted_score in compliance_summary.

---

## 3. Phase 1 — Extract

- **Input:** snapshot_path + execution metadata (execution_job_id, tenant_id, account_id, query_id, run_at).
- **Action:** Load S3 JSON → upsert rows into `execution_snapshot_rows`. Compute `snapshot_hash` (e.g. SHA-256 of normalized snapshot content) per execution or per row for audit.
- **Output:** Snapshot table ready for evaluation. Idempotent by (execution_job_id, row_index).

---

## 4. Phase 2 — Evaluation

- **Input:** execution_job_id + query metadata (framework, control_ref, pass_rule, required_columns, severity, rule_version).
- **Action:**
  - Read `execution_snapshot_rows` for the job.
  - Apply pass_rule via **pluggable Rule Engine** (zero_rows, threshold, field_check, regex, custom).
  - Build **structured evidence**: resource IDs, field values, row_index from required_columns.
  - Write `control_results` with evidence, summary, snapshot_hash, rule_version.
  - **Drift:** Compare with previous control_result for same (account_id, framework, control_id); set status_changed, previous_status if different.
- **Output:** control_results table.

---

## 5. Compliance Summary

- **Input:** control_results for tenant/account/framework/time window.
- **Action:** Aggregate:
  - total_controls_evaluated, passed_count, failed_count, pass_percentage.
  - severity_weighted_score (using severity weights from config).
- **Output:** compliance_summary table. Refresh on new control_results or on schedule.

---

## 6. Drift Detection (built-in)

- Compare latest control_results with previous evaluation for same (account_id, framework, control_id).
- Set status_changed = true and previous_status when status differs.
- Store for reporting and Risk Engine (e.g. “control X regressed from passed to failed”).

---

## 7. API / Dashboard Layer

- **List control_results:** Filters: tenant_id, account_id, framework, status, time range, control_id.
- **List compliance_summary:** Filters: tenant_id, account_id, framework, period (period_start/period_end).
- **Get evidence for control_result:** Return structured evidence (JSONB + normalized control_evidence_resources).
- **List snapshot rows for execution:** Optional; for debug and evidence inspection (execution_job_id).
- **Time-first / historical:** Support query by run_at range or by snapshot_hash for replay.
- **GET /controls:** List controls (from controls table) with title, severity, remediation, service. Dashboard can show remediation text.
- **POST /simulate (policy simulation mode):** Body: `{ "snapshot_hash": "...", "rule_version": "next" }`. Run evaluation **without persisting** (no insert into control_results). Return would-be control_results and evidence. Lets customers test new policies before enforcing. Future differentiator.

---

## 8. Pluggable Rule Engine

| Rule type | Description |
|-----------|-------------|
| zero_rows | Pass if row count = 0; else fail. Evidence: list of row_data keys (required_columns). |
| threshold | Pass if numeric field op threshold (e.g. count &lt;= N). |
| field_check | Pass if field value matches (e.g. encrypted = true). |
| regex | Pass if field matches regex. |
| custom | Expression or script; pluggable handler. |

Registry: rule_type → handler. Adding a new type does not require rewriting the engine.

---

## 9. Jobs / Orchestration

- **Event-driven:** Trigger evaluation when new snapshot is available (webhook from execution platform or queue message: execution_job_id + snapshot_path).
- **Batch / backfill:** Process multiple executions; support parallel workers (e.g. by tenant or account).
- **Worker pool:** Consume from queue; run Phase 1 then Phase 2 per execution; write control_results, then refresh compliance_summary (or separate summary job).

---

## 11. Control Relationships (optional — see control_dependencies table)

- **parent_control_id** in control_results: link child control to parent (e.g. for dashboards and “control group” rollups).
- Config: control_id → parent_control_id for framework. Use for dependency tracking and advanced dashboards.

---

## 12. Tests & Validation

- **Unit tests:** Fixture snapshots (0 rows = pass; N rows = fail with evidence). Validate evidence structure and summary.
- **Idempotency:** Re-run Phase 1 + Phase 2 on same execution → same control_results; snapshot_hash stable.
- **Snapshot_hash:** Verify same snapshot content produces same hash; different content different hash.
- **Drift:** Fixture: previous control_result passed, current failed → status_changed true, previous_status = passed.
- **Severity-weighted score:** Fixture control_results with mixed severity → compliance_summary severity_weighted_score correct.

---

## 13. Implementation roadmap (phased)

**MVP+ (next 2 weeks)** — Ship fast, enterprise-ready baseline:

- **controls** table (control definitions: title, description, severity, remediation, service, default_weight, enabled).
- **control_state** table (current state cache: account_id, control_id, latest_status, last_run_at, last_snapshot_hash).
- **Evidence normalization:** control_evidence_resources table; write both JSONB evidence and normalized rows (resource_id, resource_type, key_field, key_value).
- **rule_definition_hash** (SHA256 of rule JSON) in control_results and rule_versions; store alongside snapshot_hash, framework_version for audit proof.

**Phase 2 (after launch)** — Scale and differentiate:

- **Change events stream:** Emit event when status_changed = true; Risk engine subscribes.
- **control_dependencies** table; rollup and dependency-aware dashboards.
- **framework_control_mappings** table; cross-framework coverage (CIS v6 ↔ v5 ↔ SOC2).
- **Partitioning:** two-level (tenant_id LIST + run_at RANGE).
- **Materialized view** mv_latest_control_status; refresh async; dashboards use it + control_state (not full history).
- **POST /simulate:** Policy simulation mode (evaluate without persisting).
- **Hash chain (tamper protection):** evaluation_hash on evaluation_runs; SLA monitoring; control_metrics; observability (OpenTelemetry); risk_tier multiplier; control scoping (scope_type, scope_value) and maturity_level; continuous compliance (delta-based).

---

## 14. Implementation Order (Cursor)

1. **Schema:** **evaluation_runs**, **snapshots** (metadata), execution_snapshot_rows (+ snapshot_id, archived_at), **controls** (+ scope_type, scope_value, maturity_level, cloud_provider), **control_state**, control_results (+ evaluation_run_id, rule_definition_hash, cloud_provider, archived_at), compliance_summary, **control_evidence_resources**, **control_dependencies**, **framework_control_mappings**, **control_metrics**; optional rule_versions, framework_versions. **Materialized view** mv_latest_control_status. **RLS** on tenant-scoped tables. **Partial index** idx_failed_controls. **Partitioning:** control_results by run_at then tenant_id (Phase 2). Alembic migrations.
2. **Config:** Control mapping (CIS v6 + severity), pass_rule definitions, severity weights.
3. **Phase 1 — Extract:** Load S3 → **snapshots** (metadata) + execution_snapshot_rows; **canonical** snapshot_hash. Create **evaluation_run** (status=running) before Phase 2.
4. **Phase 2 — Evaluator:** Read snapshot rows; **freeze rule JSON** in context; pluggable rule engine; evidence builder (store only required fields in evidence JSONB); write control_results + **control_evidence_resources**; update **control_state**; drift detection; update **evaluation_runs** (completed_at, status=completed/failed); **control_metrics**; emit **change event** when status_changed.
5. **Compliance summary job:** Aggregate control_results → compliance_summary; severity_weighted_score.
6. **API:** List control_results, compliance_summary, evidence (JSONB + normalized), snapshot rows; **GET /controls**; **POST /simulate** (Phase 2).
7. **Orchestration:** Event-driven trigger + batch worker; queue or webhook; event stream on status_changed.
8. **Tests:** Fixtures for pass/fail, idempotency, snapshot_hash, rule_definition_hash, drift, severity, control_state, evidence normalization.
9. **Docs:** Architecture diagram (docs/ARCHITECTURE_DIAGRAM.md), runbook, CIS v6 reference.

---

## 15. Out of Scope

- Running Steampipe or Powerpipe (execution platform).
- Risk scoring logic (Risk Engine).
- Full UI implementation (API contract only).

---

Use this document as the **single source of truth** for the Cloud Compliance Engine. For the full visual blueprint (Phase 1 → Phase 2, tables, rule engine, drift, API, event-driven), see **docs/ARCHITECTURE_DIAGRAM.md**.
