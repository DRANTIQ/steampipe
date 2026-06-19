# How to Fit the Production Job Engine Into Our Code and Project

This guide maps the production job engine (batches, trigger-tenant, scheduler, worker, content_hash) **into our existing codebase** and ties it to **what we already discussed** (queries doc, 17 queries, scheduling, scale, run patterns). Use it as the implementation map.

---

## 1. How it fits our ideas (recap)

| We discussed | How the production engine fits |
|--------------|--------------------------------|
| **17 queries in data/queries.json, apply script** | Same; add **content_hash** when we save/apply queries (QUERY_FINALISED_CHANGES). |
| **Trigger for tenant: all accounts, all providers** | **POST /executions/trigger-tenant** implements this; creates one batch and jobs in chunks of 200; enforces daily limit. |
| **Schedule: all queries × all accounts (Way 1, then Way 2)** | Scheduler keeps “one schedule per query” and adds **run_all**; when run_all=true we load all queries and create jobs in chunks; each run creates one **ExecutionBatch** (schedule_id, scheduled_at) for idempotency. |
| **Bulk cap 200, no overload** | Chunk size 200 everywhere (trigger-tenant, scheduler); re-use **BULK_QUERY_IDS_MAX**. |
| **One job = one query × one account** | Unchanged; jobs get **batch_id** when created by trigger-tenant or scheduler; single/bulk API leave batch_id null. |
| **S3 snapshots, later extract → CIS/control** | Unchanged; worker still writes snapshot to S3; batch/engine is about **creating and tracking jobs**, not changing the snapshot flow. |

So: the production engine **sits on top of** our current execution model (Steampipe → job → snapshot); it adds batching, tenant trigger, daily limits, and safer worker behaviour.

---

## 2. File-by-file: where each piece goes

### 2.1 New files

| File | Purpose |
|------|--------|
| `alembic/versions/002_production_job_engine.py` | New migration: execution_batches, batch_id, content_hash, run_all, scheduled_at, indexes. |
| `src/models/execution_batch.py` | Model for `execution_batches` table (id, tenant_id, schedule_id, scheduled_at, trigger_type, total_jobs, completed_jobs, failed_jobs, status, created_at, finished_at). |

### 2.2 Existing files to change

| File | Changes |
|------|---------|
| **src/models/__init__.py** | Import and export `ExecutionBatch`. |
| **src/models/execution_job.py** | Add `batch_id` (FK to execution_batches, nullable), relationship to ExecutionBatch. |
| **src/models/query.py** | Add `content_hash` (String(64), nullable). |
| **src/models/query_schedule.py** | Add `run_all` (Boolean, default False); make `query_id` nullable. |
| **src/api/schemas.py** | Already have ExecutionTriggerTenantCreate/Response; add batch_id, total_jobs, etc. Add ExecutionBatchResponse if we list batches. |
| **src/api/routes/executions.py** | Add **POST /trigger-tenant** (validate tenant, load accounts/queries, daily limit, create batch, create jobs in chunks of 200, push queue, return batch_id + total_jobs). Optionally **GET /batches** or **GET /executions?batch_id=**. |
| **src/scheduler/cron_scheduler.py** | For each due schedule: (1) idempotency check (batch for schedule_id + scheduled_at); (2) if run_all load all queries else one query; (3) create ExecutionBatch (schedule_id, scheduled_at, trigger_type=schedule); (4) create jobs in chunks of 200 with batch_id; push each chunk to queue; (5) update next_run_at. |
| **src/workers/execution_worker.py** | (1) After pop from Redis: **atomic claim** (UPDATE job SET status='running', started_at=now() WHERE id=? AND status IN ('queued','retrying') RETURNING *; if 0 rows, skip). (2) On **failure**: if retry_count < max_retries then set status=queued, retry_count += 1, push to Redis; else mark failed. (3) On **finish** (success or fail): if job.batch_id then update batch (increment completed_jobs or failed_jobs; if total reached set status and finished_at). |
| **scripts/apply_queries_document.py** | When building Query or updating: compute **content_hash** (normalize query_text, SHA-256), set on row. |
| **src/api/routes/queries.py** | On create/update query: compute and set **content_hash** (shared helper: normalize + hash). |
| **src/config/settings.py** | Already has BULK_QUERY_IDS_MAX; use it for chunk size (no new setting). |

### 2.3 Where not to change

| Area | Why |
|------|-----|
| **Snapshot flow** (SnapshotService, S3 path) | Unchanged; worker still calls persist_snapshot and writes ExecutionResult. |
| **Queue** (QueueService) | Same push(job_id, payload); trigger-tenant and scheduler call it per job in the chunk. |
| **Tenants, accounts, queries API** | Only queries: add content_hash to response and to create/update logic. |
| **Single/bulk execution endpoints** | Unchanged; they don’t create a batch (batch_id stays null). |

---

## 3. Step-by-step integration (order to implement)

### Phase A — Schema and models

1. **Migration 002**  
   - Create table `execution_batches` (id, tenant_id, schedule_id, **scheduled_at**, trigger_type, total_jobs, completed_jobs, failed_jobs, status, created_at, finished_at).  
   - Add `execution_jobs.batch_id` (nullable FK to execution_batches), index.  
   - Add `queries.content_hash` (varchar 64, nullable).  
   - Add `query_schedules.run_all` (boolean default false), `query_schedules.query_id` nullable.  
   - Indexes: execution_batches (tenant_id, status, schedule_id); execution_jobs (status, batch_id, (tenant_id, status)); query_schedules (enabled, next_run_at); queries partial index optional.

2. **Model ExecutionBatch**  
   - New file `src/models/execution_batch.py` with table name, columns, relationships (tenant, schedule, jobs).  
   - Enums: batch status (running, completed, failed, partial) — can be string or small enum.

3. **Models: link and fields**  
   - `ExecutionJob.batch_id` (nullable FK), relationship to ExecutionBatch.  
   - `Query.content_hash`.  
   - `QuerySchedule.run_all`, `query_id` nullable.  
   - `models/__init__.py`: import and export ExecutionBatch.

### Phase B — Trigger-tenant and daily limit

4. **Helper: daily job count**  
   - In `executions.py` or a small service: `count_tenant_jobs_today(session, tenant_id)` (created_at >= today 00:00 UTC). Use for both trigger-tenant and (optionally) bulk.

5. **POST /executions/trigger-tenant**  
   - In `src/api/routes/executions.py`: new route.  
   - Validate tenant (exists, active).  
   - Load active accounts (tenant_id, active=true, deleted_at null).  
   - Load active queries (deleted_at null, active=true).  
   - Build (account, query) pairs where account.provider == query.provider.  
   - total_jobs = len(pairs). If count_tenant_jobs_today + total_jobs > tenant.max_executions_per_day → 429/400 with message.  
   - Create ExecutionBatch (tenant_id, trigger_type=manual, total_jobs=total_jobs, status=running).  
   - Loop pairs in chunks of 200 (BULK_QUERY_IDS_MAX): create ExecutionJob rows with batch_id, push each job_id to queue, session.commit() per chunk.  
   - Return { batch_id, total_jobs } (and optionally job_ids if small).

### Phase C — Scheduler

6. **Scheduler: idempotency and run_all**  
   - In `cron_scheduler.py`: for each due schedule, before creating jobs:  
     - scheduled_at = s.next_run_at (store for batch).  
     - Check if batch already exists (schedule_id=s.id, scheduled_at in same window, e.g. same minute). If yes, skip (idempotent).  
   - If s.run_all: load all active queries (for that tenant’s provider mix, or all and filter by account.provider when building pairs).  
   - Else: load single query by s.query_id.  
   - Create ExecutionBatch (tenant_id, schedule_id, scheduled_at, trigger_type=schedule, total_jobs=…).  
   - Create jobs in chunks of 200 with batch_id; push to queue; commit per chunk.  
   - Then set s.last_run_at, s.next_run_at.

### Phase D — Worker

7. **Worker: atomic claim**  
   - In `execution_worker.py`, at start of process_job: after getting job_id from payload, do  
     `session.execute(UPDATE execution_jobs SET status='running', started_at=now() WHERE id=:id AND status IN ('queued','retrying') RETURNING id)`;  
     if no row returned, log and return (already claimed).  
   - Then load job again (or use returned row) and continue as today.

8. **Worker: retry on failure**  
   - Where we set job.status = failed and create ExecutionResult:  
     - If job.retry_count < job.max_retries: set status=queued, retry_count += 1, commit, queue.push(job_id, payload), return.  
     - Else: mark failed and create failed result as today.

9. **Worker: batch update on finish**  
   - After creating ExecutionResult and setting job.status (success/failed):  
     - If job.batch_id:  
       - If success: UPDATE execution_batches SET completed_jobs = completed_jobs + 1 WHERE id = :batch_id RETURNING completed_jobs, failed_jobs, total_jobs.  
       - If failed: same with failed_jobs.  
       - If returned row has (completed_jobs + failed_jobs) >= total_jobs: UPDATE execution_batches SET status = completed|failed|partial, finished_at = now() WHERE id = :batch_id.

### Phase E — Content hash

10. **Content hash on queries**  
    - Add small helper: `normalize_query_text(text) -> str` (strip, collapse whitespace, maybe trim semicolon), then `content_hash = hashlib.sha256(normalize_query_text(text).encode()).hexdigest()`.  
    - In `apply_queries_document.py`: when creating/updating Query, set content_hash.  
    - In `queries.py` create/update: same; include content_hash in QueryResponse if needed.

---

## 4. Ties to our other docs

| Doc | Link |
|-----|-----|
| **Production spec and review** | [PRODUCTION_JOB_ENGINE_SPEC_AND_REVIEW.md](PRODUCTION_JOB_ENGINE_SPEC_AND_REVIEW.md) — full spec and corrections. |
| **What’s implemented today** | [CODE_STATUS_AND_FEATURES_TO_ADD.md](CODE_STATUS_AND_FEATURES_TO_ADD.md) — update “trigger-tenant” and “batch” rows once done. |
| **Query storage and finalised changes** | [QUERY_FINALISED_CHANGES.md](QUERY_FINALISED_CHANGES.md) — content_hash was already planned. |
| **Scheduling and run patterns** | [SCHEDULING_AND_EXECUTION.md](SCHEDULING_AND_EXECUTION.md), [RUN_ALL_QUERIES_ALL_ACCOUNTS_SCHEDULE.md](RUN_ALL_QUERIES_ALL_ACCOUNTS_SCHEDULE.md) — run_all and chunking implement “Way 2” and scale. |
| **Plan summary** | [PLAN_AND_IMPLEMENTATION_SUMMARY.md](PLAN_AND_IMPLEMENTATION_SUMMARY.md) — update when batch and trigger-tenant are done. |

---

## 5. Checklist (fit into our project)

- [ ] Migration 002: execution_batches (+ scheduled_at), batch_id on execution_jobs, content_hash on queries, run_all + nullable query_id on query_schedules, indexes.  
- [ ] Model ExecutionBatch; ExecutionJob.batch_id; Query.content_hash; QuerySchedule.run_all, query_id nullable.  
- [ ] Trigger-tenant: validate tenant, load accounts/queries, daily limit, create batch, chunked job creation (200), push queue.  
- [ ] Scheduler: idempotency (schedule_id + scheduled_at), run_all branch, create batch, chunked jobs with batch_id.  
- [ ] Worker: atomic claim (UPDATE … queued/retrying); retry requeue; batch update on completion.  
- [ ] Content hash: set in apply_queries_document and in queries create/update.  
- [ ] Single/bulk executions unchanged (batch_id null).  
- [ ] Update CODE_STATUS_AND_FEATURES_TO_ADD and PLAN_AND_IMPLEMENTATION_SUMMARY when shipped.

This is how the production job engine fits into our code and project as per our ideas and discussions.
