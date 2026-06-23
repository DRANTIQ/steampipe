# Steampipe Platform — Scaling Phases Roadmap

**Status:** Phase 0 complete (2026-06-20). End-to-end execution works: assume-role, Steampipe query, local snapshot.

**When to revisit:** Before bulk compliance scans, when the queue backlog grows, or before production multi-tenant deploy.

---

## Phase 0 — Stabilize (DONE)

**Goal:** Jobs succeed reliably in Docker.

**Changes made:**

- Removed `platform: linux/arm64` from compose files (use host native amd64/arm64)
- Rebuild: `docker compose -f docker-compose.remote.yml build --no-cache`
- `AWS_EC2_METADATA_DISABLED=true` on worker (prevents AWS SDK from hanging on EC2 metadata in Docker)
- Connection diagnostics in worker on query failure

**Verify:** `Job ... success` in worker logs; snapshot under `local/snapshots/`.

```bash
docker compose -f docker-compose.remote.yml exec worker uname -m
# Intel Windows: x86_64 (not aarch64)
```

---

## Phase 1 — Horizontal scale (more workers)

**Goal:** Process more jobs in parallel without code changes.

**When to implement:**

- Jobs sit `queued` while the worker is busy
- Multiple tenants or schedules firing together

**How:**

```bash
docker compose -f docker-compose.remote.yml up --scale worker=3
```

**Effort:** Minutes  
**Speedup:** ~N× throughput (N = worker replica count)  
**Code changes:** None required

---

## Phase 2 — Warm Steampipe service

**Goal:** Start Steampipe once per worker process; reuse for each job (swap `.spc` / creds only).

**When to implement:**

- Dozens or hundreds of jobs per day
- Fixed per-job overhead (~40s init wait + service restart) dominates total runtime

**Implement:**

- Refactor `run_worker_loop()` / `_run_steampipe_query()` in `src/workers/execution_worker.py`
- Do not stop/start Steampipe service on every job
- Restart service on connection error or every N jobs (e.g. 50)

**Effort:** ~1–2 weeks  
**Speedup:** ~2× per worker (less fixed wait; no full service restart per job)

---

## Phase 3 — Account session (bulk queries)

**Goal:** One AssumeRole + one Steampipe init per account; run many queries in one session.

**When to implement:**

- `POST /api/v1/executions/bulk` with many query IDs
- Full CIS/compliance run (~49–200 queries per account)
- Scheduler “run all queries for provider/account”

**Implement:**

- Worker groups jobs by `(batch_id, account_id)` or processes a batch as a unit
- Loop queries inside one Steampipe session
- Still write one `ExecutionResult` per query (API unchanged)

**Effort:** ~2–4 weeks  
**Speedup:** ~3–5× for bulk scans on one account

**Example:** 49 queries × ~75s/job (Phase 0) ≈ 1 hour → Phase 3 ≈ 15–25 minutes

---

## Phase 4 — Job-per-container (K8s / ECS)

**Goal:** Orchestrator pops Redis and spawns a container per job or per account session; auto-scale on demand.

**When to implement:**

- Production on AWS (ECS/EKS)
- Many tenants; strict isolation between runs
- Elastic scale beyond fixed `docker compose --scale`

**Implement:**

- Job runner service or Step Functions / K8s Jobs
- Best combined with Phase 3 (one container = one account session, not one query)

**Effort:** Infra project (weeks)

---

## Recommended implementation order

| Priority | Phase | Trigger |
|----------|-------|---------|
| Done | **0** | Steampipe init / Docker arch |
| As needed | **1** | Queue backlog, jobs waiting in `queued` |
| Before bulk compliance | **3** | Bulk API, run-all schedules |
| High single-worker volume | **2** | Per-job overhead hurts before or after Phase 3 |
| Production deploy | **4** | K8s/ECS, multi-tenant SLA |

---

## Rough timing estimates

Assumptions: ~75s per job on Phase 0 (includes ~40s connection init wait + ~30s query).

| Jobs | Phase 0 (1 worker) | Phase 1 (3 workers) | Phase 3 (1 account session) |
|------|--------------------|---------------------|-----------------------------|
| 10 | ~12 min | ~4 min | ~5 min |
| 49 | ~1 h | ~20 min | ~15–25 min |
| 200 | ~4.2 h | ~1.4 h | ~30–60 min (depends on query mix) |
| 1000 | ~21 h | ~7 h | Batch by account; see Phase 3 design |

Heavy CIS queries (2–5 min each) increase all totals; Phase 3 helps most when init overhead dominates.

---

## Current architecture (Phase 0)

Each job:

1. Build temp config `run_{job_id}/` (`.spc` + credentials from DB account + AssumeRole)
2. Stop/start Steampipe service on port 9194
3. Wait `STEAMPIPE_CONNECTION_INIT_WAIT_SECONDS` (default 45; `.env` may override)
4. Run `steampipe query --search-path <connection_name>`
5. Persist snapshot; update `execution_jobs` / `execution_results`
6. Tear down service and temp config

Only the **worker** runs Steampipe. API and scheduler enqueue jobs only.

### Phase C (implemented): account session

When `STEAMPIPE_ACCOUNT_SESSION_ENABLED=true` and jobs share a `batch_id` + `account_id` (e.g. CIS scan):

1. API creates jobs in Postgres, commits, then pushes **one Redis message** per `(batch_id, account_id)` (`mode: account_session`)
2. One worker acquires a Redis lock, claims all queued jobs from DB
3. One AssumeRole + one Steampipe service start
4. Runs all queries with warm service (`skip_service_start` / `keep_service_alive`)
5. Other workers handle other accounts/batches in parallel; they do not split one account scan

See [CIS_SCAN_RUNBOOK.md](CIS_SCAN_RUNBOOK.md).

---

## Notes for future implementers

- `MAX_CONCURRENT_EXECUTIONS` in `.env` is documented but **not wired** in code; parallel work = worker replica count (Phase 1).
- Tune `STEAMPIPE_CONNECTION_INIT_WAIT_SECONDS` down (e.g. 20–30) only after stable success on native Docker arch.
- SSO `AWS_SESSION_TOKEN` in `.env` expires; refresh for dev or use IAM task/instance role in production.
- Bulk API cap: `BULK_QUERY_IDS_MAX` (default 200) — see [SCALE_OVERLOAD_CLARIFICATION.md](SCALE_OVERLOAD_CLARIFICATION.md).
- Per-job Steampipe lifecycle: [STEAMPIPE_CONNECTIONS_AND_WORKSPACES.md](STEAMPIPE_CONNECTIONS_AND_WORKSPACES.md) §8.

---

## Related docs

| Doc | Topic |
|-----|-------|
| [STAGE1_FULL_GUIDE.md](STAGE1_FULL_GUIDE.md) | Architecture, APIs, run flow |
| [SCALE_OVERLOAD_CLARIFICATION.md](SCALE_OVERLOAD_CLARIFICATION.md) | Bulk caps, queue overload |
| [SCHEDULING_AND_EXECUTION.md](SCHEDULING_AND_EXECUTION.md) | Bulk vs run-all patterns |
| [RUN_WITH_REMOTE_DB.md](RUN_WITH_REMOTE_DB.md) | Docker + Supabase + Upstash |
