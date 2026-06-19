# Code Status (What the Code Is Up To) and Features To Add

Single reference: **where the code is today** and **what features still need to be added**.

---

## Part 1: What the code is up to (current implementation)

### API (FastAPI)

| Area | Endpoint / behaviour | Status |
|------|----------------------|--------|
| **Tenants** | `POST /api/v1/tenants`, `GET /api/v1/tenants`, `GET /api/v1/tenants/{id}` | Implemented |
| **Accounts** | `POST /api/v1/tenants/{tenant_id}/accounts`, `GET /api/v1/tenants/{tenant_id}/accounts` | Implemented |
| **Queries** | `POST /api/v1/queries`, `GET /api/v1/queries` (with optional `provider`, `active`) | Implemented |
| **Schedules** | `POST /api/v1/schedules`, `GET /api/v1/schedules` (optional `tenant_id`, `enabled`) | Implemented |
| **Executions** | `POST /api/v1/executions` (single: one query, one account) | Implemented |
| **Executions** | `POST /api/v1/executions/bulk` (many queries, one account; cap 200 query_ids) | Implemented |
| **Executions** | `GET /api/v1/executions`, `GET /api/v1/executions/{job_id}` | Implemented |
| **Executions** | `GET /api/v1/executions/{job_id}/result`, `GET /api/v1/executions/{job_id}/result/data` | Implemented |
| **Executions** | `POST /api/v1/executions/trigger-tenant` (trigger all queries, all accounts, for tenant; daily limit enforced) | Implemented |

### Worker and scheduler

| Component | What it does | Status |
|-----------|--------------|--------|
| **Execution worker** | Atomic claim; runs Steampipe per job; snapshot to S3; retry/requeue on failure; batch completion updates (ExecutionBatch). | Implemented |
| **Scheduler** | Idempotency; run_all (nullable query_id); ExecutionBatch per run; jobs in chunks of 200; updates next_run_at. | Implemented |

### Data and scripts

| Item | What it does | Status |
|------|--------------|--------|
| **DB schema** | Tenants, users, api_keys, cloud_accounts, queries (content_hash), query_schedules (run_all, nullable query_id), execution_jobs (batch_id), execution_batches, execution_results (Alembic 001 + 002). | Implemented |
| **data/queries.json** | 17 queries; apply script loads into `queries` table with content_hash. | Implemented |
| **scripts/apply_queries_document.py** | Reads data/queries.json; upserts into `queries` by (name, version); sets content_hash. | Implemented |
| **Bulk cap** | `BULK_QUERY_IDS_MAX` (default 200); bulk endpoint returns 400 if exceeded. | Implemented |

### What the code does **not** do yet

- No **extract** step (read snapshot JSON from S3 → write into DB tables for analysis).
- No **control / CIS / SOC2** evaluation or pass/fail or alarms.

---

## Part 2: Features to add

### High priority (agreed in design)

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 1 | **Trigger for tenant** | `POST /api/v1/executions/trigger-tenant` with `tenant_id`; daily limit; ExecutionBatch; jobs in chunks of 200. | **Done** |

### When scaling (100+ queries, many accounts)

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 2 | **Run all schedule (Way 2)** | query_schedules.run_all + nullable query_id; when cron fires, create jobs for (all queries × all accounts) in batches. | **Done** |
| 3 | **Scheduler batching (Way 4)** | Create jobs in chunks of 200, commit and push per chunk; idempotency per (schedule_id, scheduled_at). | **Done** |

### Optional (schema / ops)

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 4 | **Query table: content_hash** | content_hash (SHA-256 of normalized query_text) in apply script and query create API. | **Done** |
| 5 | **Tenant execution limits** | max_executions_per_day enforced in trigger-tenant; 429 when exceeded. | **Done** |

### Later (analysis and compliance)

| # | Feature | Description |
|---|---------|-------------|
| 6 | **Extract snapshot to DB** | Process: read snapshot JSON from S3 (path from ExecutionResult); write rows into analysis/snapshot tables (by execution, query, account). |
| 7 | **Control / CIS / SOC2 evaluation** | Evaluate stored snapshot data against rules (using required_columns, pass_rule); write control_results (or similar); pass/fail per control. |
| 8 | **Alarms** | Use control_results to trigger alarms (e.g. per control, per account, per tenant). |

---

## Part 3: Quick reference

| Category | Code is up to… | To add |
|----------|----------------|--------|
| **API** | Tenants, accounts, queries (with content_hash), schedules, single + bulk + **trigger-tenant** (daily limit), list/get execution and result/result/data. | — |
| **Worker** | Atomic claim, Steampipe run, snapshot to S3, ExecutionResult, **retry/requeue**, **batch completion** updates. | — |
| **Scheduler** | Idempotency, **run_all**, ExecutionBatch, jobs in chunks of 200 per schedule. | — |
| **Data** | 17 queries + apply script with content_hash; schema 001 + 002 (execution_batches, batch_id, content_hash, run_all). | — |
| **Downstream** | — | Extract → DB; control evaluation; alarms. |

Use this doc to see **until what the code is up to** and **what features need to be added**.
