# Scale and Overload — Clarification Before Implementation

**Process:** First agree on (1) what “overload” means, (2) when it happens, and (3) the best solution. Then implement only what we agree on.

---

## 1. Is it actually overload? When?

**“Overload”** here means the system (queue, worker, DB) is stressed or unusable when we create **many jobs at once** (e.g. one job per query for 10,000 queries on one account).

| Component | Risk when 10k jobs created at once | Notes |
|-----------|------------------------------------|--------|
| **Redis queue** | 10k items in one go is usually fine for Redis; memory and latency are typically OK. | Overload more likely from **processing** than from enqueue. |
| **Worker** | One worker processes jobs one-by-one. 10k jobs = long tail; new work waits. Other tenants/accounts are delayed. | This is **latency/throughput**, not necessarily “crash.” |
| **DB** | 10k INSERTs (ExecutionJob) + later 10k INSERTs (ExecutionResult) in a short time. Can cause connection pool exhaustion or lock contention if done in one transaction or very fast. | Depends on DB size and connection limits. |
| **Steampipe** | One Steampipe run per job; no 10k Steampipe processes at once if workers are limited. | Worker concurrency (e.g. 3) naturally limits parallel Steampipe runs. |

So “overload” is mainly:

- **Queue/worker:** Very long backlog; other work is delayed (fairness, latency).
- **DB:** Possible connection or write spike if we’re not careful (e.g. one huge transaction vs many small commits).
- **API:** One request creating 10k rows and 10k queue pushes can be slow and tie up the API; timeouts or connection issues.

It’s not necessarily “system crash” but **degraded behavior and risk** under spike load. We should define what we want to prevent (e.g. “no single request creating > N jobs” or “no more than M queued jobs per tenant”).

---

## 2. How can we overcome it? Options

| Option | What it does | Pros | Cons |
|--------|----------------|------|------|
| **A. Cap bulk request size** | Reject bulk if `len(query_ids) > N` (e.g. 200). Client must batch. | Simple, prevents one request from creating 10k jobs. | Client must implement batching; arbitrary limit. |
| **B. No cap; client batches** | No server-side limit. Rely on client to send e.g. 200 at a time. | No server change; flexible. | One bad or naive client can still send 10k and stress the system. |
| **C. Async / background “run all”** | New endpoint: “run these 10k queries for this account.” Server creates jobs in background in chunks (e.g. 200 per batch, small delay). Returns a “batch_id” or “run_id”; client polls. | Single client call; server controls rate. | More implementation (background job, status, polling). |
| **D. Rate limit per tenant** | Allow e.g. max 500 queued jobs per tenant; reject new bulk if would exceed. | Protects queue and fairness. | Need to count “queued” per tenant; may reject legitimate large runs. |
| **E. Scheduler staggering** | When many schedules fire, spread job creation over time (e.g. 100 jobs per minute per schedule). | Avoids scheduler-induced spike. | Scheduler logic gets more complex; runs may complete later. |
| **F. Queue priority + fairness** | Multiple queues or priority so one tenant’s 10k jobs don’t starve others. | Fairness. | More infra (queues, workers per queue). |

We can combine: e.g. **A + B** (cap + document client batching), or **A + D** (cap + per-tenant limit), or **C** if we want a “run all” UX without client batching.

---

## 3. What is the best solution? (To agree before implementing)

- **Minimal:** **A (cap)** + **documentation** that for large N the client should batch (e.g. 200 per request). No other code. Revert cap if we decide we don’t want it.
- **Medium:** **A** + **D** (cap + per-tenant queued limit) so one tenant can’t flood the queue even with many small bulk calls.
- **Richer:** **C** (async “run all” with server-side batching) so one API call can trigger 10k queries without the client batching; we control rate.

**Recommendation to agree on:** Start with **minimal (A + doc)** unless we need per-tenant protection (then add D) or “run all” UX (then add C). After we agree, we either keep the current cap implementation, remove it, or add the chosen extra (D or C).

---

## 4. Current state (what was implemented before this clarification)

- **BULK_QUERY_IDS_MAX = 200** in settings; bulk endpoint returns 400 if `len(query_ids) > 200`.
- **Doc:** SCHEDULING_AND_EXECUTION.md §5 describes scale, cap, and batching.

If we agree the best solution is **“cap + client batching”**, we keep this. If we prefer **no server cap** (rely on client), we remove the cap. If we prefer **async run-all** or **per-tenant limit**, we add that and can keep or drop the cap as we agree.

---

## 5. Next step

Please confirm:

1. Do we consider “one request creating 10k jobs” a problem we want to prevent (yes/no)?
2. Which approach do you want: **A only**, **A + D**, **C**, or **no cap (B)**?
3. Only after that we **implement** (or revert) accordingly.
