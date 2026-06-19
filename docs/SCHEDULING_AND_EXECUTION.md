# Scheduling and Execution — How It Works

How to **schedule** queries, what **execution_mode: single_account** means, how queries are applied to **all AWS accounts**, and how the **scheduler** works for different jobs.

---

## 1. Execution mode: single_account

- Every query in our catalog has **execution_mode: single_account**.
- Meaning: **one execution job = one query run against one cloud account.** The worker runs Steampipe with that query for that account’s connection only.
- To run the same query on **multiple accounts**, we create **multiple jobs** (one per account). To run **multiple queries** on one account, we create **multiple jobs** (one per query).

So: **all queries can be applied to all AWS accounts** by creating one job per (query, account). We do that via the API (single, bulk) or the scheduler.

---

## 2. How to run queries (on-demand)

### Single execution (one query, one account)

```http
POST /api/v1/executions
Content-Type: application/json

{
  "tenant_id": "<tenant_id>",
  "account_id": "<account_id>",
  "query_id": "<query_id>",
  "priority": 0,
  "triggered_by": "manual"
}
```

Returns `job_id`. Poll `GET /api/v1/executions/{job_id}` until `status` is `success` or `failed`; then `GET /api/v1/executions/{job_id}/result` and `/result/data` for the snapshot.

### Bulk: all 17 queries on one account

```http
POST /api/v1/executions/bulk
Content-Type: application/json

{
  "tenant_id": "<tenant_id>",
  "account_id": "<account_id>",
  "query_ids": ["<id1>", "<id2>", ... ],
  "priority": 0,
  "triggered_by": "manual"
}
```

Creates **one job per query** for that account. Pass all 17 query IDs (from `GET /api/v1/queries`) to run the full set on that account.

### Run one query on all accounts (manual)

Call `POST /api/v1/executions` once per account with the same `query_id` (or add a small script that lists accounts and creates one execution per account).

---

## 2b. Run patterns: batch (all for provider/account) vs subset (10 or 20 queries)

**Run all queries as a batch for a provider for an account**

- **Meaning:** For one account (e.g. AWS account X), run **every query** that belongs to that **provider** (e.g. `aws`) in one go — i.e. a single “batch run” for that provider on that account.
- **How (on-demand):**
  1. `GET /api/v1/queries?provider=aws&limit=500` → get all query IDs for that provider.
  2. `POST /api/v1/executions/bulk` with `tenant_id`, that `account_id`, and **all** those query IDs. If there are more than 200 queries, call bulk **multiple times** with batches of 200 (API cap).
- **How (scheduled):** When we add the “run all” schedule (Way 2), the scheduler will do this for every account on cron — i.e. “run all queries for provider X” per account as a batch. Until then, use one schedule per query (Way 1) or trigger bulk via API/script per account.

**Run a subset (e.g. 10 or 20 queries) — manual**

- **Meaning:** Run only selected queries on one account (e.g. 10 or 20 specific checks).
- **Best way:** `POST /api/v1/executions/bulk` with that `tenant_id`, `account_id`, and **only the 10 or 20 query_ids** you want. One request; creates 10 or 20 jobs. No need to call single execution 10 times.
- **Alternative:** Call `POST /api/v1/executions` 10 times (one per query). Works but bulk is simpler and one round-trip.

So: **batch = all queries for provider for account** (bulk with all provider query IDs, or scheduler “run all”); **subset = manual via bulk** with the 10 or 20 query_ids you need.

---

## 3. How to schedule queries

### Create a schedule (API)

```http
POST /api/v1/schedules
Content-Type: application/json

{
  "tenant_id": "<tenant_id>",   // optional if only one tenant; else required
  "query_id": "<query_id>",
  "cron_expression": "0 */6 * * *",   // every 6 hours
  "timezone": "UTC",
  "enabled": true
}
```

- **One schedule** = one (tenant, query) + cron. When the schedule fires, the scheduler creates **one execution job per account** for that tenant (all active AWS accounts that match the query’s provider). So a single schedule runs that query on **all AWS accounts** for the tenant every 6 hours (or whatever cron you set).

### List schedules

```http
GET /api/v1/schedules?tenant_id=<tenant_id>&enabled=true
```

### Scheduler process

- Run the **scheduler** (separate process): `python -m src.cli scheduler` or `./scripts/run_scheduler.sh`.
- It wakes every **1 minute**, loads schedules where `next_run_at <= now` and `enabled = true`, and for each:
  - Loads the query and finds **all** cloud accounts for that tenant with the same provider (e.g. `aws`).
  - Creates **one ExecutionJob per account** (same query, different account), pushes each to the queue, updates `next_run_at` for the schedule.
- The **worker** (separate process) picks jobs from the queue and runs Steampipe; each job is independent (one query, one account).

So: **different “works”** = different jobs. Each schedule can produce many jobs (one per account). The worker processes jobs one-by-one (or in parallel if you run multiple workers). No cross-job state; each job has its own result and snapshot.

---

## 4. Summary

| Goal | How |
|------|-----|
| Run one query on one account | `POST /api/v1/executions` with that query_id and account_id. |
| Run all 17 queries on one account | `POST /api/v1/executions/bulk` with that account_id and all 17 query_ids. |
| Run one query on all AWS accounts (on-demand) | Multiple `POST /api/v1/executions` (one per account), or script over accounts. |
| Run one query on all AWS accounts on a schedule | `POST /api/v1/schedules` with that query_id and desired cron. Scheduler creates one job per account when it fires. |
| Run all 17 queries on all accounts on a schedule | Create 17 schedules (one per query); each fires and creates one job per account. |

**Execution mode** = single_account → one job = one query × one account. **All queries applied to all AWS accounts** = create jobs for every (query, account) pair, either via bulk + multiple accounts, or via one schedule per query (scheduler creates jobs for all accounts).

---

## 5. Scale and overload: many queries (e.g. 10,000) per account

If you create **one job per query** and have **10,000 queries** for one account, doing that in one shot can overload the system:

- **Queue:** 10,000 messages at once can stress Redis and delay other work.
- **Worker:** Jobs are processed one-by-one (per worker). 10k jobs = long tail; other tenants/accounts wait.
- **DB:** 10k `ExecutionJob` rows + 10k `ExecutionResult` rows in a short time; possible connection or lock pressure.

**Mitigations:**

1. **Cap bulk size:** The API limits how many queries you can submit in one bulk request (**default 200**, configurable via `BULK_QUERY_IDS_MAX`). For 10,000 queries, call bulk **in batches** (e.g. 50 requests × 200 query_ids), optionally with a short delay between batches, so the worker can drain the queue.
2. **Stagger schedules:** If many schedules fire in the same minute (e.g. one schedule per query), the scheduler creates (queries × accounts) jobs at once. To avoid spikes, stagger cron times (e.g. different minutes or use a scheduler that spreads jobs over time) or limit how many schedules are due in the same run.
3. **Worker concurrency:** Run more workers to process jobs in parallel. Each worker still does one job at a time; more workers = higher throughput and faster drain. Avoid running so many workers that Steampipe/DB become the bottleneck.
4. **Tenant/account limits:** Enforce `max_executions_per_day` (or a per-tenant queue depth limit) so one tenant cannot flood the queue. Optional: reject or defer bulk create when the tenant already has too many queued jobs.

So: **one job per query is fine for 17 or hundreds of queries** if you batch bulk requests and/or stagger schedules. For **10,000 queries**, don’t submit them all in one bulk call; use the cap (200 per request by default) and batch, and consider staggering schedule times so the system doesn’t get a single huge spike.
