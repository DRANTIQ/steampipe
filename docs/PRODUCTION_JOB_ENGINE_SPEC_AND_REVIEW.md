# Production-Grade Job Engine — Spec, Fit with Base, and Review

**Goal:** Production-grade job engine: Steampipe execution per tenant, batched jobs, safe concurrency, S3 snapshots, daily execution limits, content hash for deduplication.

This doc: (1) your spec in structured form, (2) how it fits our codebase, (3) improvements and corrections, (4) implementation order.

---

## Part 1 — Your spec (structured)

### 1.1 Migrations / schema

| Change | Detail |
|--------|--------|
| **New table: execution_batches** | id (uuid PK), tenant_id (FK tenants, not null), schedule_id (FK query_schedules, nullable), trigger_type (varchar 32: manual/schedule/api), total_jobs (int default 0), completed_jobs (int default 0), failed_jobs (int default 0), status (varchar 32: running/completed/failed/partial, default 'running'), created_at, finished_at (nullable). Indexes: tenant_id, status, schedule_id. |
| **execution_jobs** | Add batch_id (FK execution_batches.id). Spec said "not null" — see review. Index: batch_id. |
| **queries** | Add content_hash (e.g. varchar 64, nullable). Optional partial index (provider, active) WHERE active = true AND deleted_at IS NULL. |
| **query_schedules** | Add run_all (boolean default false). query_id nullable when run_all = true. |

### 1.2 Trigger-tenant endpoint

- **POST /api/v1/executions/trigger-tenant**, body: `{ "tenant_id": "uuid" }`.
- Steps: validate tenant (exists, active); load active accounts (tenant, active, not deleted); load active queries; filter by provider (query.provider == account.provider); enforce tenant daily limit (count today’s jobs, reject if would exceed max_executions_per_day); optional dedupe by content_hash (skip query if same content_hash already executed today); create ExecutionBatch (trigger_type=manual); create jobs in chunks of 200 (bulk insert, push to queue, commit per chunk); return `{ "batch_id", "total_jobs" }`.

### 1.3 Scheduler

- Same chunk logic (200) when creating jobs; create one ExecutionBatch per run (schedule_id set, trigger_type=schedule).
- Idempotency: skip if batch already exists for (schedule_id, scheduled_at).
- run_all on query_schedules: if run_all=true, fetch all active queries; else use query_id.

### 1.4 Worker

- Atomically claim: UPDATE execution_jobs SET status='running', started_at=now() WHERE id = (SELECT id FROM execution_jobs WHERE status='queued' ... LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *.
- Retry: on failure increment retry_count; if retry_count < max_retries, requeue (set status=queued, push to Redis); else mark failed.

### 1.5 Job completion and batch update

- On job finish: update execution_results; increment batch.completed_jobs or failed_jobs; if completed_jobs + failed_jobs == total_jobs, set batch.status (completed/failed/partial) and finished_at.

### 1.6 Indexes

- execution_jobs: status; (tenant_id, status); batch_id.
- query_schedules: (enabled, next_run_at).
- queries: partial (provider, active) WHERE active AND deleted_at IS NULL.

---

## Part 2 — Fit with our base

| Your item | Our codebase | Fit |
|-----------|--------------|-----|
| execution_batches | New table. We have execution_jobs, execution_results; no batch today. | Add new model + migration. |
| execution_jobs.batch_id | Not null in spec. We have single/bulk executions that don’t use a batch. | **Make batch_id nullable.** For trigger-tenant and scheduler we always set batch_id; for POST /executions and POST /executions/bulk leave batch_id null (or create a single-job batch per call — nullable is simpler). |
| Tenant daily limit | Tenant has max_executions_per_day (default 100). We have _check_tenant_limits() but it doesn’t enforce yet. | Use in trigger-tenant: count jobs where tenant_id and created_at >= today; if count + total_jobs we’d create > max, reject (429/400). |
| content_hash | Not on Query today. QUERY_FINALISED_CHANGES already planned it. | Add column; compute on apply_queries_document and on query create/update (normalize query_text then SHA-256). |
| run_all on schedules | QuerySchedule has query_id NOT NULL. | Migration: add run_all (default false), make query_id nullable. When run_all=true, query_id can be null. |
| Idempotency (schedule) | Need “scheduled_at” for the run. execution_batches has created_at. | **Add scheduled_at (timestamptz, nullable)** to execution_batches. For schedule runs set scheduled_at = schedule’s next_run_at (before advancing). Unique (schedule_id, scheduled_at) WHERE schedule_id IS NOT NULL, or check before create. |
| Worker claim | We currently pop job_id from Redis, then load job with with_for_update. Two workers get different job_ids from Redis. | **Option A (minimal):** Keep Redis; when worker starts processing do UPDATE execution_jobs SET status='running', started_at=now() WHERE id=? AND status IN ('queued','retrying') RETURNING *; if 0 rows, skip (already claimed). **Option B (DB-driven):** Worker claims from DB with FOR UPDATE SKIP LOCKED, then pushes to “in progress”; more invasive. Recommend Option A for our base. |
| Retry | We have retry_count, max_retries on ExecutionJob. Worker currently marks failed without requeue. | On failure: if retry_count < max_retries then set status=queued, retry_count += 1, push job_id to Redis; else mark failed. |
| Batch update on finish | We don’t have batches yet. On job success/fail we write ExecutionResult and set job.status. | After commit of result, if job.batch_id: UPDATE execution_batches SET completed_jobs = completed_jobs + 1 (or failed_jobs), then if completed_jobs + failed_jobs = total_jobs set status and finished_at. Use single UPDATE with RETURNING or two statements to avoid race. |
| Queue push | We use QueueService.push(job_id, payload). | Unchanged; trigger-tenant and scheduler push each job_id in the chunk after bulk insert. |

---

## Part 3 — Improvements and corrections

| # | Item | Suggestion / correction |
|---|------|--------------------------|
| 1 | **batch_id not null** | Make **batch_id nullable**. Existing single/bulk flows don’t create a batch; backward compatible. |
| 2 | **execution_batches.scheduled_at** | **Add column** scheduled_at (timestamptz, nullable). For schedule-triggered batches set scheduled_at = schedule’s next_run_at. Enables idempotency: “already a batch for (schedule_id, scheduled_at)” → skip. |
| 3 | **Idempotency key** | Use (schedule_id, scheduled_at). Before creating jobs for a due schedule, check if batch exists with that schedule_id and scheduled_at in the same minute (or exact match). If yes, skip creating duplicate batch/jobs. |
| 4 | **Daily limit** | Reject with **429** or **400** and message “Tenant daily execution limit exceeded” when (today’s job count + total_jobs to create) > tenant.max_executions_per_day. Don’t truncate silently. |
| 5 | **Content-hash dedupe** | Optional and heavier: “skip query if same content_hash already executed today for this tenant” requires joining execution_jobs → queries and filtering by created_at >= today. Implement as optional (e.g. query param or tenant setting); skip in v1 if you want simpler ship. |
| 6 | **Chunk size** | Align with **BULK_QUERY_IDS_MAX** (200). Use same constant for trigger-tenant and scheduler chunks. |
| 7 | **Worker atomic claim** | Prefer **lightweight claim**: after pop from Redis, UPDATE job SET status='running', started_at=now() WHERE id=? AND status IN ('queued','retrying') RETURNING *; if no row, skip. Avoids double execution if same job was pushed twice; keeps Redis as queue. |
| 8 | **Batch status** | partial = some completed, some failed (completed_jobs + failed_jobs == total_jobs but failed_jobs > 0). completed = all success; failed = all failed. |
| 9 | **Index execution_jobs.status** | We may already have tenant_id index; add composite (tenant_id, status) for “count today’s jobs per tenant” and list by status. Add index on status for worker claim. |
| 10 | **run_all and query_id** | Constraint: when run_all = false, query_id must be not null. When run_all = true, query_id can be null. Enforce in app or with CHECK. |

---

## Part 4 — Implementation order

1. **Migration 1 (execution_batches + batch_id + queries + query_schedules)**  
   - Create execution_batches (with scheduled_at).  
   - Add execution_jobs.batch_id (nullable, FK), index batch_id.  
   - Add queries.content_hash (nullable).  
   - Add query_schedules.run_all (default false), query_id nullable; optional partial index on queries.  
   - Add indexes: execution_batches (tenant_id, status, schedule_id); execution_jobs (status, (tenant_id, status)); query_schedules (enabled, next_run_at).

2. **Models**  
   - ExecutionBatch model and relationship from ExecutionJob.  
   - Query.content_hash; QuerySchedule.run_all; query_id nullable.

3. **Trigger-tenant endpoint**  
   - Validate tenant, load accounts/queries, filter by provider, check daily limit, create batch, create jobs in chunks of 200 (bulk insert, push, commit per chunk), return batch_id and total_jobs.

4. **Scheduler**  
   - For each due schedule: idempotency check (batch for schedule_id + scheduled_at); if run_all load all queries else load one query; create batch (scheduled_at = next_run_at); create jobs in chunks of 200 with batch_id; push to queue; update next_run_at.

5. **Worker**  
   - Atomic claim (UPDATE … WHERE status IN ('queued','retrying') RETURNING *); on failure retry logic (requeue if retry_count < max_retries); on finish update batch (increment completed_jobs/failed_jobs, set status/finished_at when total reached).

6. **Content hash**  
   - On query create/update (and in apply_queries_document): normalize query_text, set content_hash. Optional: content-hash dedupe in trigger-tenant.

7. **Single/bulk executions**  
   - Leave batch_id null for POST /executions and POST /executions/bulk (no batch created). Optional later: create a one-job batch per execution for uniformity.

---

## Part 5 — Summary: what to add

| Area | Add / change |
|------|----------------|
| **Schema** | execution_batches (+ scheduled_at); execution_jobs.batch_id (nullable); queries.content_hash; query_schedules.run_all, query_id nullable; indexes as above. |
| **API** | POST /executions/trigger-tenant (validate tenant, daily limit, batch, chunked job creation). |
| **Scheduler** | Idempotency; run_all branch; create batch with scheduled_at; chunked job creation with batch_id. |
| **Worker** | Atomic claim (UPDATE … queued/retrying); retry requeue; on job finish update batch (completed_jobs/failed_jobs, status, finished_at). |
| **Content hash** | Set on query write; optional dedupe in trigger-tenant. |

This doc is the single reference to implement the production job engine in our base and incorporates your spec plus the improvements above.
