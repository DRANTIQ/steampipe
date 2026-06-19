# Cloud Compliance Engine — Full Architecture Diagram

Ready-to-implement blueprint: Phase 1 → Phase 2, tables, rule engine, evidence, drift, API, event-driven triggers.

---

## 1. High-level flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  EXECUTION PLATFORM (Steampipe)                                                  │
│  execution_jobs, execution_results.snapshot_path, queries.extra_metadata         │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │ event: "job done" + snapshot_path + metadata
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  EVENT QUEUE / WEBHOOK                                                            │
│  (Redis, SQS, or HTTP POST)                                                       │
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│  Worker 1           │   │  Worker 2           │   │  Worker N           │
│  (parallel pool)    │   │                     │   │                     │
└──────────┬──────────┘   └──────────┬──────────┘   └──────────┬──────────┘
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  COMPLIANCE ENGINE (this repo)                                                    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │  EVALUATION RUN (lifecycle)                                                  ││
│  │  INSERT evaluation_runs (status=running, snapshot_hash, tenant_id,         ││
│  │    account_id, cloud_provider, framework). completed_at/status set at end.  ││
│  └─────────────────────────────────────────────┬───────────────────────────────┘│
│                                                │                                 │
│  ┌─────────────────────────────────────────────▼───────────────────────────────┐│
│  │  PHASE 1 — EXTRACT                                                           ││
│  │  Input: snapshot_path, execution_job_id, tenant_id, account_id, query_id,   ││
│  │         run_at                                                               ││
│  │  Action: GET S3 JSON → canonical hash → snapshots + execution_snapshot_rows  ││
│  │  Output: snapshots (metadata), execution_snapshot_rows (DB). No hard delete. ││
│  └─────────────────────────────────────────────┬───────────────────────────────┘│
│                                                │                                 │
│                                                ▼                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │  PHASE 2 — RULES (Pluggable Rule Engine)                                     ││
│  │  Freeze rule JSON in context; canonical hash. evaluation_run_id on results.  ││
│  │  Action: READ execution_snapshot_rows → pass_rule → evidence (required only) ││
│  │          → control_results + control_evidence_resources + control_state       ││
│  │          → drift; control_metrics; evaluation_runs.completed_at, status     ││
│  │  Output: control_results (DB). RLS on tenant_id. Partial index on failed.    ││
│  └─────────────────────────────────────────────┬───────────────────────────────┘│
│                                                │                                 │
│                                                ▼                                 │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │  COMPLIANCE SUMMARY (aggregation)                                             ││
│  │  Input: control_results (tenant, account, framework, period)                  ││
│  │  Action: SUM passed/failed, pass_percentage, severity_weighted_score         ││
│  │  Output: compliance_summary (DB)                                             ││
│  └─────────────────────────────────────────────┬───────────────────────────────┘│
└────────────────────────────────────────────────┼────────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  API LAYER                                                                       │
│  GET /control_results  GET /compliance_summary  GET /evidence  GET /snapshot_rows│
└─────────────────────────────────────┬───────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  RISK ENGINE (next)  →  DASHBOARD                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data model (tables)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  controls (control definitions — first-class)                                    │
├──────────────────────────────────────────────────────────────────────────────────┤
│  id, control_id, framework, title, description, severity, remediation, service,  │
│  default_weight, enabled. UNIQUE(framework, control_id)                           │
└──────────────────────────────────────────────────────────────────────────────────┘
                                        │
┌──────────────────────────────────────────────────────────────────────────────────┐
│  execution_snapshot_rows (Phase 1)                                                │
├──────────────────────────────────────────────────────────────────────────────────┤
│  id, execution_job_id, tenant_id, account_id, query_id, run_at, row_index,       │
│  row_data (JSONB), snapshot_hash. UNIQUE(execution_job_id, row_index)             │
└──────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        │ 1 execution → N rows
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  control_results (Phase 2) — partition by run_at (monthly) at scale                │
├──────────────────────────────────────────────────────────────────────────────────┤
│  id, tenant_id, account_id, execution_job_id, snapshot_path, snapshot_hash,       │
│  rule_definition_hash, framework, framework_version, control_id, control_ref,   │
│  parent_control_id, status, severity, rule_version, evaluated_at, run_at,         │
│  evidence (JSONB), summary, status_changed, previous_status                      │
└──────────────────────────────────────────────────────────────────────────────────┘
         │                                          │
         │ update                                    │ 1 result → N evidence rows
         ▼                                          ▼
┌─────────────────────────────┐    ┌──────────────────────────────────────────────┐
│  control_state (cache)      │    │  control_evidence_resources (normalized)       │
├─────────────────────────────┤    ├──────────────────────────────────────────────┤
│  account_id, control_id,    │    │  control_result_id, resource_id, resource_type,│
│  framework, latest_status,   │    │  key_field, key_value                          │
│  last_run_at,               │    │  → "show all failed S3 buckets across tenants"  │
│  last_snapshot_hash         │    └──────────────────────────────────────────────┘
└─────────────────────────────┘
                                        │
                                        │ aggregate by tenant/account/framework/period
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  compliance_summary                                                               │
├──────────────────────────────────────────────────────────────────────────────────┤
│  id, tenant_id, account_id, framework, control_id, period_start, period_end,      │
│  total_controls_evaluated, passed_count, failed_count, pass_percentage,           │
│  severity_weighted_score, last_evaluated_at                                       │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│  control_dependencies          │  framework_control_mappings                      │
│  parent_control_id,            │  source_framework, source_control_id,            │
│  child_control_id, framework   │  target_framework, target_control_id             │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│  mv_latest_control_status (materialized view)                                     │
│  DISTINCT ON (account_id, framework, control_id) * FROM control_results           │
│  ORDER BY account_id, framework, control_id, run_at DESC → refresh async           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Rule engine & evidence mapping

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PLUGGABLE RULE ENGINE                                                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  execution_snapshot_rows (for execution_job_id)                                  │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                │
│  │ zero_rows        │  │ threshold       │  │ field_check      │                │
│  │ count == 0 → pass│  │ field op value  │  │ field == expected│                │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘                │
│           │                    │                    │                           │
│           └────────────────────┼────────────────────┘                           │
│                                ▼                                                │
│  ┌─────────────────┐  ┌─────────────────┐                                       │
│  │ regex            │  │ custom          │  ← registry: rule_type → handler     │
│  │ field ~ pattern  │  │ expression      │                                       │
│  └────────┬────────┘  └────────┬────────┘                                       │
│           │                    │                                                │
│           └────────────────────┼────────────────────────────────┘              │
│                                ▼                                                │
│  EVIDENCE BUILDER                                                                │
│  • From row_data + required_columns → extract resource IDs, key fields          │
│  • Structure: [{ "resource_id": "...", "field": "value", "row_index": 0 }, ...]  │
│  • Summary: one-line actionable text (e.g. "3 buckets with versioning disabled") │
│                                │                                                │
│                                ▼                                                │
│  control_results row (status, evidence, summary, rule_version, snapshot_hash)   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Drift detection

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  DRIFT DETECTION                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Before writing new control_result for (account_id, framework, control_id):      │
│                                                                                  │
│  1. SELECT previous control_result for same (account_id, framework, control_id)  │
│     ORDER BY run_at DESC LIMIT 1                                                 │
│                                                                                  │
│  2. If previous exists and previous.status != current.status:                    │
│     • Set status_changed = true                                                  │
│     • Set previous_status = previous.status                                      │
│     • (Optional) emit event for Risk Engine / alerts                             │
│                                                                                  │
│  3. INSERT/UPDATE control_results with status_changed, previous_status           │
│                                                                                  │
│  Use case: "Control 2.1.1 regressed from passed to failed" in dashboard / API   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Event-driven triggers

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  TRIGGERS                                                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Option A — Queue (recommended)                                                  │
│  Execution platform → push message { execution_job_id, snapshot_path, metadata } │
│  → Compliance workers BLPOP / consume → Phase 1 → Phase 2 → compliance_summary  │
│                                                                                  │
│  Option B — Webhook                                                              │
│  Execution platform → POST /evaluate { execution_job_id, snapshot_path, ... }    │
│  → Compliance API → enqueue or run sync → Phase 1 → Phase 2                     │
│                                                                                  │
│  Option C — Polling                                                              │
│  Compliance worker polls execution_results (snapshot_path NOT NULL, no control_  │
│  result yet) → Phase 1 → Phase 2                                                 │
│                                                                                  │
│  Batch / backfill: same pipeline; feed list of execution_job_ids (e.g. from DB   │
│  or CSV); parallel workers by tenant or account.                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Change events stream

When **status_changed = true**, emit event (tenant_id, account_id, control_id, previous_status, current_status, severity) → Redis/SQS/Kafka → Risk Engine subscribes.

---

## 7. API & dashboard layer

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  API ENDPOINTS                                                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  GET /control_results                                                            │
│    ?tenant_id=&account_id=&framework=&status=&control_id=&run_at_from=&run_at_to │
│    → List control_results (paginated)                                            │
│                                                                                  │
│  GET /compliance_summary                                                         │
│    ?tenant_id=&account_id=&framework=&period_start=&period_end                   │
│    → List compliance_summary (tenant or account level)                           │
│                                                                                  │
│  GET /control_results/:id/evidence                                                │
│    → Structured evidence (resource IDs, fields) for that control_result         │
│                                                                                  │
│  GET /executions/:execution_job_id/snapshot_rows                                 │
│    → List execution_snapshot_rows (debug / evidence inspection)                 │
│                                                                                  │
│  GET /controls   → controls table (title, severity, remediation, service)        │
│  POST /evaluate   Body: { execution_job_id, snapshot_path, ... }               │
│  POST /simulate   Body: { snapshot_hash, rule_version }  → evaluate WITHOUT     │
│                    persisting (policy test). Dashboards: mv_latest_control_status│
│  Time-first / historical: run_at and period filters on all list endpoints        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. One-page blueprint summary

| Layer | Component | Input | Output |
|-------|-----------|--------|--------|
| Trigger | Event queue / webhook | execution_job_id, snapshot_path, metadata | Message to workers |
| Phase 1 | Extract | S3 path, execution metadata | execution_snapshot_rows, snapshot_hash |
| Phase 2 | Rule engine | execution_snapshot_rows, pass_rule, required_columns | status, evidence, summary, rule_definition_hash |
| Phase 2 | Drift | previous control_result, new status | status_changed, previous_status |
| Phase 2 | Write | Evaluator output | control_results, control_evidence_resources, control_state |
| Phase 2 | Event | status_changed = true | Change event → Risk Engine |
| Aggregation | Summary job | control_results | compliance_summary (severity_weighted_score) |
| Perf | Materialized view | control_results | mv_latest_control_status (refresh async) |
| API | REST | Filters | control_results, compliance_summary, evidence, controls; POST /simulate |
| Next | Risk Engine / Dashboard | control_results, compliance_summary, events | Risk scores, UI |

---

This diagram is the **ready-to-implement blueprint** for the dev team. Implement in the order given in PROMPT.md §14; phased rollout in §13 (MVP+ then Phase 2).
