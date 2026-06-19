# Plan and Implementation Summary

One-place summary of **what we plan** and **what we have implemented so far** from our discussions.

---

## 1. Product / platform goals

- **Cloud governance and cost intelligence** using Steampipe (query AWS and other clouds via SQL).
- **Multi-tenant:** Tenants have cloud accounts; we run queries per account and store results (snapshots).
- **Flow:** Run Steampipe queries → snapshot JSON to S3 → later: extract to DB → evaluate controls (CIS/SOC2-style) → pass/fail and alarms. We **do not run Powerpipe** (AGPL); we use Steampipe only and our own control logic.
- **Scale:** Today 17 queries; later 100 or 10k queries, multiple accounts and tenants. Design must support batching and “run all” so we don’t overload.

---

## 2. What we planned (design / docs)

| Area | Plan | Where it’s written |
|------|------|--------------------|
| **Licensing** | Powerpipe = reference only (AGPL). Steampipe + plugins = we use (Apache-2.0). Our stored queries = Steampipe SQL only; CIS/framework in metadata = our labels for reference. | QUERIES_AND_COMPLIANCE_DESIGN.md |
| **Query storage** | One row per query; `query_text` (SQL), `extra_metadata` (framework, control_ref, required_columns, pass_rule). Optional: content_hash, tenant_id, status. | QUERY_STORAGE_IDEAS.md, QUERY_FINALISED_CHANGES.md |
| **Queries document** | Single JSON file (`data/queries.json`) applied to `queries` table; 17 queries for now. Apply via script. | QUERIES_DOCUMENT_SPEC.md, data/queries.json |
| **Catalog & columns** | QUERIES_CATALOG.md = list of all queries. Required columns per query for CIS/control evaluation; REAL_SAAS_DATA_FLOW_AND_COLUMNS.md = flow and column list. | QUERIES_CATALOG.md, REAL_SAAS_DATA_FLOW_AND_COLUMNS.md |
| **Execution model** | One job = one query × one account. “All queries, all accounts” = many jobs (one per pair). | SCHEDULING_AND_EXECUTION.md |
| **Scheduling** | Way 1 (now): one schedule per query per tenant, same cron; scheduler creates one job per account when cron fires. Way 2 (later): one “run all” schedule per tenant, batched job creation. Way 3: stagger. Way 4: scheduler-side batching. | RUN_ALL_QUERIES_ALL_ACCOUNTS_SCHEDULE.md |
| **Scale / overload** | Bulk API capped (e.g. 200 query_ids per request). At 100 queries: add batching or “run all”. At 10k queries: must use “run all” + batching; no “one schedule per query”. | SCALE_OVERLOAD_CLARIFICATION.md, SCHEDULING_AND_EXECUTION.md §5, RUN_ALL_QUERIES_ALL_ACCOUNTS_SCHEDULE.md §6–7 |
| **Run patterns** | Batch = all queries for a provider for one account (GET queries by provider → bulk). Subset = 10 or 20 queries via one bulk request. Trigger for tenant = one trigger runs all queries on all accounts (all providers) for that tenant. | SCHEDULING_AND_EXECUTION.md §2b |

---

## 3. What we have implemented (code)

| Component | Implemented | Notes |
|-----------|--------------|--------|
| **Query table & model** | Yes | Existing: name, version, provider, plugin, query_text, execution_mode, output_format, extra_metadata, etc. |
| **Queries document + apply** | Yes | `data/queries.json` (17 queries); `scripts/apply_queries_document.py` loads JSON and upserts into `queries` by (name, version). |
| **Execution: single** | Yes | `POST /api/v1/executions` — one query, one account. |
| **Execution: bulk** | Yes | `POST /api/v1/executions/bulk` — list of query_ids, one account; creates one job per query. Capped at `BULK_QUERY_IDS_MAX` (default 200). |
| **Scheduler** | Yes | Scheduler process runs every minute; for each due schedule (tenant + query), creates **one job per account** for that tenant (all accounts matching query’s provider). |
| **Bulk cap** | Yes | `BULK_QUERY_IDS_MAX` in settings; bulk endpoint returns 400 if `len(query_ids) > cap`. |
| **Trigger for tenant** | Yes | `POST /api/v1/executions/trigger-tenant`; daily limit; ExecutionBatch; jobs in chunks of 200. |
| **Execution batches** | Yes | execution_batches table; batch_id on jobs; worker updates completed_jobs/failed_jobs, status, finished_at. |
| **Scheduler: run_all, batching, idempotency** | Yes | query_schedules.run_all + nullable query_id; ExecutionBatch per run; jobs in chunks of 200; skip if batch exists for (schedule_id, scheduled_at). |
| **Worker: atomic claim, retry, batch update** | Yes | UPDATE status to running on claim; requeue on failure if retry_count < max_retries; _update_batch_on_job_finish on completion. |
| **Query content_hash** | Yes | content_hash in apply script and query create API; QueryResponse includes content_hash. |

**Not implemented (design only):**

- Extract step (JSON from S3 → DB) and control evaluation (CIS/SOC2 pass/fail) and alarms.

---

## 4. Summary table

| Topic | Plan | Implemented |
|-------|------|-------------|
| Queries: licensing & storage | Steampipe only; metadata for framework/control ref | Query model + 17 in data/queries.json + apply script |
| Run all as batch (provider + account) | GET queries by provider → bulk with all IDs | Yes (client does GET + bulk) |
| Run subset (10–20 queries) | One bulk with those query_ids | Yes (bulk) |
| Trigger for tenant (all accounts, all providers) | One API call; server creates jobs in batches | Yes (trigger-tenant + daily limit + ExecutionBatch) |
| Schedule: all queries × all accounts | Way 1: per-query; Way 2: run_all | Yes (run_all + nullable query_id; batches of 200) |
| Scale: 100 / 10k queries | Batching, run all schedule | Yes (scheduler batching, idempotency, worker retry) |
| Snapshot → DB → CIS/control | Documented flow | Not implemented |

---

## 5. Next implementation steps (if we continue)

1. **Extract and compliance:** Read snapshot JSON from S3 → DB; evaluate controls (CIS/SOC2); alarms.
2. **Optional:** Additional query indexes (provider, plugin; partial active + not deleted) if needed.

This is the plan and what we have implemented till now.
