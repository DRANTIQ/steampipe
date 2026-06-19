# Run All Queries on All Accounts — Per Schedule (All Tenants)

**Requirement:** Run **all queries** on **every account**, for **all tenants**, on a schedule. Options: **once per day**, or **every 6 hours**, or **every 12 hours**. Goal: get the data (snapshots) for everyone on that cadence.

Below: what “best” means here, **all viable ways** to do it, and a **recommended approach** with concrete steps.

---

## 1. Requirement in one line

- **What:** All queries × all accounts × all tenants.
- **When:** On a schedule — 1×/day, or every 6h, or every 12h.
- **Result:** Execution jobs (and then snapshots) for every (tenant, account, query) on that schedule.

---

## 2. Best ways (and other options)

### Way 1: One schedule per query per tenant (current product — no new code)

- **How:** For each tenant, create **17 schedules** (one per query). Use the **same cron** for all 17, e.g. every 6h: `0 */6 * * *`.
- **What happens:** Every 6h the scheduler finds all due schedules. For each schedule (tenant + query) it creates **one job per account** for that tenant. So every 6h you get: **17 × (number of accounts for that tenant)** jobs per tenant. Across all tenants: **17 × (total accounts)** jobs in that minute.
- **Cron examples:**
  - Once per day at 00:00 UTC: `0 0 * * *`
  - Every 6 hours: `0 */6 * * *` (00:00, 06:00, 12:00, 18:00)
  - Every 12 hours: `0 */12 * * *` (00:00, 12:00)
- **Pros:** No code change; works today. One schedule = one query, clear and simple.
- **Cons:** 17 schedule rows per tenant. If you have many tenants and many accounts, all jobs are created in the same minute (can add staggering — see Way 3).

**To do “all tenants, all accounts”:** For every tenant, create 17 schedules (one per query ID), same cron. Scheduler already creates jobs for all accounts of that tenant per schedule. So “all tenants” = create these schedules for each tenant (via API or script).

---

### Way 2: One “run all queries” schedule per tenant (new feature)

- **How:** Add a schedule type where **query_id is optional**. If “run all” is set, when the schedule fires we create jobs for **every (query, account)** for that tenant — i.e. all queries × all accounts in one go. Create jobs **in batches** (e.g. 200 at a time) so we don’t spike DB/queue.
- **What happens:** One schedule per tenant, e.g. cron `0 */6 * * *`. When it fires, load all queries (e.g. 17), all accounts for tenant; create jobs in chunks of 200, push to queue, then next chunk. Result: same set of jobs as Way 1, but one schedule row per tenant and controlled batching.
- **Pros:** One schedule per tenant; batching avoids a single huge spike; same cron for 1×/day, 6h, or 12h.
- **Cons:** Needs schema/API change (e.g. nullable `query_id` or “run_all” flag) and scheduler logic for “run all” + batching.

---

### Way 3: Stagger schedules (same as Way 1, but spread in time)

- **How:** Same as Way 1 (17 schedules per tenant), but give each of the 17 a **different minute** (or minute range) so they don’t all fire at once. E.g. query 1 at `0 */6 * * *`, query 2 at `5 */6 * * *`, query 3 at `10 */6 * * *`, … so jobs are spread over ~1 hour every 6h.
- **Pros:** Reduces spike in one minute; no new “run all” feature. Good when 17 × (total accounts) is large.
- **Cons:** “All queries” for a tenant don’t all start at the same time; full set finishes over ~1 hour. More schedule rows to manage (same 17 per tenant, different crons).

---

### Way 4: Scheduler-side batching (keep Way 1, add batching in code)

- **How:** Keep one schedule per query per tenant. When the scheduler creates jobs, don’t push all at once: create e.g. 200 jobs, flush/commit, push to queue, then next 200. So for one (tenant, query) with 1000 accounts we do 5 batches of 200.
- **Pros:** No new schedule type; less spike when one tenant has many accounts.
- **Cons:** Scheduler run can take longer (batches + optional small delay). Still 17 schedule rows per tenant.

---

## 3. Recommended approach

- **Short term (no new features):** Use **Way 1** — one schedule per query per tenant, same cron (`0 */6 * * *` or `0 0 * * *` or `0 */12 * * *`). For “all tenants, all accounts, all queries” you create 17 schedules **for each tenant**. Scheduler already creates one job per account per schedule; so every 6h (or 12h or 1×/day) you get all queries run on all accounts for all tenants.
- **If one tenant has very many accounts:** Add **Way 4** (scheduler creates jobs in batches of 200) so we don’t create 17 × 500 = 8500 jobs in one go in the same second.
- **If you want one schedule per tenant and controlled batching:** Implement **Way 2** (“run all” schedule + batched job creation).

So: **best way with current code = Way 1**; **best way overall** = Way 1 now, then add batching (Way 4) or “run all” (Way 2) if we need to reduce spikes or simplify to one schedule per tenant.

---

## 4. How to do it today (Way 1) — step by step

**Goal:** All queries run on all accounts, for all tenants, every 6 hours (or 1×/day or every 12h).

1. **Get tenant IDs and query IDs**
   - `GET /api/v1/tenants` → list of tenants.
   - `GET /api/v1/queries` → list of queries (e.g. 17); take their `id`s.

2. **Create schedules**
   - For **each tenant**, for **each query**, call:
     - `POST /api/v1/schedules`  
       Body: `{ "tenant_id": "<tenant_id>", "query_id": "<query_id>", "cron_expression": "0 */6 * * *", "timezone": "UTC", "enabled": true }`
   - Use the same `cron_expression` for all:
     - **Every 6 hours:** `0 */6 * * *`
     - **Every 12 hours:** `0 */12 * * *`
     - **Once per day (midnight UTC):** `0 0 * * *`

3. **Run the scheduler**
   - Keep the scheduler process running (`python -m src.cli scheduler` or `./scripts/run_scheduler.sh`). It runs every minute; when the clock matches the cron it will create jobs for every (query, account) for each tenant.

4. **Run the worker**
   - Workers consume the queue and run Steampipe. So for all tenants and all accounts you get the data (snapshots) as jobs complete.

**Result:** Every 6h (or 12h or 1×/day) the system creates jobs so that **all queries run on all accounts for all tenants**; when jobs finish, you have the data. No new code required for Way 1.

---

## 5. Summary table

| Way | What you do | Best for |
|-----|-------------|----------|
| **1** | 17 schedules per tenant, same cron | Use now; all tenants, all accounts, 1×/day or 6h or 12h. |
| **2** | One “run all” schedule per tenant (new feature) | One schedule per tenant; server batches job creation. |
| **3** | 17 schedules per tenant, staggered cron | Spread load over ~1 hour; avoid one-minute spike. |
| **4** | Same as 1, add batching in scheduler | Many accounts per tenant; avoid DB/queue spike. |

**Recommendation:** Implement **Way 1** for “run all queries on all accounts, per schedule, for all tenants” with cron 1×/day or 6h or 12h. Add **Way 4** (batching) or **Way 2** (run-all) later if we need to limit spikes or simplify to one schedule per tenant.

---

## 6. Future scale: ~100 queries, multiple accounts

**Today:** 17 queries. **Future:** e.g. **100 queries**, **multiple accounts** per tenant (and multiple tenants). The same design applies; numbers scale up.

| Scale | Way 1 (current) | What to add when it hurts |
|-------|------------------|---------------------------|
| **17 queries, few accounts** | 17 schedules per tenant; jobs = 17 × accounts. Fine. | Nothing. |
| **~100 queries, multiple accounts** | 100 schedules per tenant; every 6h jobs = **100 × (accounts)** per tenant. E.g. 10 tenants × 20 accounts = 100 × 200 = **20,000 jobs** in one minute. | **Way 4** (scheduler creates jobs in batches of 200) and/or **Way 2** (one “run all” schedule per tenant with batching). Optionally **Way 3** (stagger cron) to spread over time. |
| **100 queries, many accounts** | Same; e.g. 100 × 100 accounts = 10,000 jobs per tenant per run. | **Way 4** or **Way 2** so we never create 10k jobs in one go; batch (e.g. 200 at a time). Bulk API cap (200 query_ids per request) already limits manual bulk; scheduler should batch too. |

**Takeaways for future (100 queries, multiple accounts):**

1. **Way 1 still works** — you create 100 schedules per tenant (one per query), same cron. Scheduler creates 100 × (accounts) jobs per tenant when the cron fires. At scale this can mean tens of thousands of jobs in one minute; DB/queue may spike.
2. **Plan for batching:** Before you grow to 100 queries and many accounts, add either **Way 4** (scheduler creates jobs in batches of 200, commit/push, then next batch) or **Way 2** (one “run all” schedule per tenant; server creates (queries × accounts) jobs in batches). Then 100 × 100 = 10,000 jobs are created in ~50 batches of 200 instead of one shot.
3. **Bulk API:** Already capped at 200 query_ids per request; for on-demand “run all 100 queries on this account” the client calls bulk in batches (e.g. 2 requests of 50, or 1 of 100 if we ever raise the cap slightly).
4. **Operational:** More workers = more throughput. Monitor queue depth and job completion time; add workers or batching so “all queries × all accounts” for all tenants finishes within your target window (e.g. within 6h before the next run).

So: **17 now, 100 later** — same model (one job per query per account). At 100 queries and multiple accounts, add **scheduler batching (Way 4)** or **“run all” schedule (Way 2)** so we don’t overload when creating jobs.

---

## 7. Very large scale: 10,000 queries

**If we have 10,000 queries**, Way 1 (one schedule per query per tenant) is **not viable**:

- **10,000 schedule rows per tenant** — heavy to create, manage, and for the scheduler to evaluate every minute.
- **When they fire:** 10,000 × (accounts) jobs in one go. E.g. 10k × 50 accounts = **500,000 jobs** per tenant in one minute → DB and queue overload.

**What we need at 10k queries:**

| Need | Approach |
|------|----------|
| **Don’t use 10k schedules** | Use **one “run all” schedule per tenant** (Way 2). When it fires, load all query IDs (or in chunks from DB), create jobs for (queries × accounts) **in batches** (e.g. 200–500 per batch). No “one schedule per query” at this scale. |
| **Job creation** | Batched: e.g. 10k × 100 accounts = 1M jobs. Create and push in batches of 200–500; commit DB and push to queue per batch. Scheduler run may take minutes (e.g. 1M ÷ 200 = 5000 batches); that’s acceptable. |
| **Worker capacity** | 1M jobs at e.g. 1 min/job = 1M worker-minutes. To finish within 6h (360 min) you need ~2,800 workers in parallel, or accept that a full run takes many hours and overlap with the next run. In practice: scale workers (tens to hundreds), and/or **split queries** (e.g. run 2k queries this window, 2k next, or run by “query pack”) so total jobs per 6h stay within what your workers can do. |
| **Bulk API** | Stay capped (e.g. 200 per request). “Run all 10k queries on this account” = 50 bulk requests of 200 query_ids. Or an async “run all for account” endpoint that creates jobs in batches server-side. |

**Summary for 10,000 queries:**

- **Way 1 is out.** Use **Way 2 only**: one “run all” schedule per tenant; on fire, create (queries × accounts) jobs in batches.
- **Batching is mandatory** — both for creating jobs and for not overloading DB/queue.
- **Throughput** — scale workers and/or split work (e.g. by query pack or time window) so “all 10k × all accounts” either completes within your schedule window or is explicitly split across windows.

So: **17 → 100 → 10k** — at 10k we **must** have the “run all” schedule (Way 2) and batched job creation; one schedule per query does not scale to 10k.
