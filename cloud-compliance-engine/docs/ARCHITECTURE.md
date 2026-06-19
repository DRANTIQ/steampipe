# Cloud Compliance Engine — Architecture

**Pattern:** Modular monolith with a clear domain boundary. Same PostgreSQL and Redis as the execution platform; compliance data lives in a dedicated schema and queue namespace.

---

## Infrastructure

| Layer | Approach |
|-------|----------|
| **PostgreSQL** | Same instance, **separate schema** `compliance` |
| **Redis** | Same instance, **separate key/queue** e.g. `compliance:job_completed` (or Redis DB number) |
| **S3** | Same bucket (read snapshots written by execution worker) |

---

## Schema Layout

```
public.execution_jobs
public.execution_results
public.queries
public.cloud_accounts
...

compliance.execution_snapshot_rows   ← Phase 1 extract (JSONB row_data, snapshot_hash)
compliance.control_results           ← Phase 2 results (evidence JSONB)
compliance.control_evidence_resources ← Column-wise for fast search/dashboards
compliance.compliance_summary        ← Aggregation
```

**Tenant/account isolation:** Hybrid design — `execution_job_id` (FK) + denormalized `tenant_id`, `account_id` in all compliance tables. Ownership propagated from `execution_jobs` at write time; fast filtering without JOINs.

---

## Why Not a Separate DB (for now)

- Compliance **consumes** snapshots and **writes** derived results; it uses the same tenant/account/job context.
- Splitting DB today would require duplicating metadata in events, losing JOINs, and maintaining two migration trees without clear benefit at MVP scale.
- Using a **schema** gives logical isolation and a simple path to a separate DB later: dump `compliance` → restore elsewhere.

---

## Redis Namespace

Use a dedicated key/queue for job-completion events consumed by the compliance engine, e.g.:

- Queue name: `compliance:job_completed`
- Or Redis logical DB: e.g. `SELECT 2` so compliance workers use DB 2.

Same Redis instance; no extra infrastructure.

---

## References

- **S3 → Postgres mapping:** [S3_TO_POSTGRES_MAPPING.md](S3_TO_POSTGRES_MAPPING.md)
- **Extract vs engine:** [ARCHITECTURE_EXTRACT_VS_ENGINE.md](ARCHITECTURE_EXTRACT_VS_ENGINE.md)
- **Full diagram:** [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)
