# Architecture

How the Cloud Compliance Engine fits with Stage 1 (Steampipe execution) and what happens on each CIS scan.

---

## 1. System context

```
┌─────────────────────────────────────────────────────────────────┐
│                        CUSTOMER / UI                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
┌─────────────────┐                    ┌─────────────────┐
│  Stage 1 API    │                    │ Compliance API  │
│  :8000          │                    │ :8001           │
│  Trigger scans  │                    │ Scan scores     │
└────────┬────────┘                    └────────▲────────┘
         │                                      │
         ▼                                      │
┌─────────────────┐     Redis events    ┌──────┴──────────┐
│ Steampipe       │ ──────────────────► │ Compliance      │
│ Worker          │  job_completed      │ Worker            │
└────────┬────────┘                     └────────┬──────────┘
         │                                      │
         ▼                                      ▼
┌─────────────────┐                    ┌─────────────────┐
│ Bronze snapshots│ ◄── read ──────────│ Postgres        │
│ (local / S3)    │                    │ compliance.*    │
└─────────────────┘                    └─────────────────┘
```

**Boundary:** Stage 1 **collects** evidence. Stage 2 **judges** it. They share Postgres and snapshot files but are separate processes.

---

## 2. End-to-end flow (one CIS scan)

### Phase A — Collection (Stage 1)

1. `POST /api/v1/executions/scan` with `framework_id=cis_aws_v6`
2. API creates `execution_batches` + 35 `execution_jobs`
3. One Redis message (`account_session`) → one worker runs all queries
4. For each control:
   - Steampipe SQL from `public.queries` (loaded from `data/queries.json`)
   - Write `result.json` under `{batch_id}/{job_id}/`
   - Insert `execution_results.snapshot_path`
   - Publish Redis event to `steampipe:job_completed`

### Phase B — Compliance (Stage 2)

For each Redis event where `category=compliance`:

1. **Compliance worker** pops event
2. **`process_job_completed`** orchestrates:
   - `get_or_create_scan_run` — one row per batch in `compliance.scan_runs`
   - `extract_snapshot_to_db` — read JSON → `snapshots` + `execution_snapshot_rows`
   - `evaluate_snapshot` — apply `pass_rule` → `control_results`
   - `record_control_evaluated` + `maybe_finalize_scan_run` — score when 35/35 done

### Phase C — Customer read (Compliance API)

- `GET /v1/scan-runs/{batch_id}` — 27 pass, 8 fail, 77%
- `GET /v1/scan-runs/{batch_id}/controls` — matrix
- `GET /v1/control-results/{id}/evidence` — failing resources

---

## 3. Medallion data layers

| Layer | Storage | Example |
|-------|---------|---------|
| **Bronze** | File: `local/snapshots/.../batch_id/job_id/result.json` | Raw Steampipe rows + metadata |
| **Silver** | `compliance.snapshots`, `execution_snapshot_rows` | Parsed rows, hashes, lineage |
| **Gold** | `scan_runs`, `control_results`, `control_state` | PASS/FAIL, score, latest posture |

**Lineage:**

```
execution_batches.id  =  scan_runs.batch_id
execution_jobs.id     =  snapshots.execution_job_id
Bronze rows           =  execution_snapshot_rows.payload
control_ref           =  rule key → control_results
```

---

## 4. Event contract (Redis)

**Queue:** `steampipe:job_completed` (configurable via `COMPLIANCE_QUEUE_KEY`)

```json
{
  "execution_job_id": "uuid",
  "snapshot_path": "local/snapshots/.../result.json",
  "tenant_id": "uuid",
  "account_id": "uuid",
  "batch_id": "uuid",
  "framework_id": "cis_aws_v6",
  "control_ref": "security-hub-enabled",
  "control_id": "5.16",
  "category": "compliance",
  "row_count": 34
}
```

---

## 5. Rule engine

Rules are **not** separate SQL files. They come from `data/queries.json` → `public.queries.extra_metadata`:

| Field | Purpose |
|-------|---------|
| `control_ref` | Rule lookup key |
| `control_id` | CIS ID (e.g. 5.16) |
| `pass_rule` | `zero_rows` = 0 rows PASS, any row FAIL |
| `required_columns` | Evidence fields for UI |

Control **labels** (title, severity, remediation) come from `config/cis_v6_controls.yaml` → `compliance.controls`.

**Evaluation:**

```
row_count = len(execution_snapshot_rows for snapshot)
status = PASS if row_count == 0 else FAIL   # zero_rows
```

CIS queries return **violations** as rows. Empty result = compliant.

---

## 6. Database schema (compliance)

| Table | Role |
|-------|------|
| `scan_runs` | One CIS scan = one batch; score, status |
| `snapshots` | Silver metadata per job snapshot |
| `execution_snapshot_rows` | Silver row payloads (JSONB) |
| `evaluation_runs` | Per-control evaluation attempt |
| `control_results` | PASS/FAIL + evidence |
| `control_evidence_resources` | Searchable resources (bucket, region, …) |
| `control_state` | Latest status per account/control |
| `controls` | Seeded catalog (YAML) |
| `compliance_summary` | Aggregates per scan or run |

Stage 1 tables live in `public` schema (`execution_jobs`, `execution_batches`, `queries`).

---

## 7. Idempotency and safety

- **Extract:** Skip if `snapshots.execution_job_id` already exists
- **Evaluate:** Skip if `idempotency_key` = `{job_id}:{control_ref}` already evaluated
- **Scan run:** One row per `(tenant_id, batch_id)` unique constraint

Re-running backfill on the same batch is safe.

---

## 8. Docker services

| Service | Port | Image command |
|---------|------|---------------|
| `api` | 8000 | Stage 1 FastAPI |
| `worker` | — | Steampipe execution worker |
| `compliance-api` | 8001 | Compliance FastAPI |
| `compliance-worker` | — | Redis consumer |

All use the same `.env` (`DATABASE_URL`, `REDIS_URL`, `LOCAL_STORAGE_PATH`).

---

## 9. Related docs

- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) — code-level walkthrough
- [API.md](API.md) — REST reference
- [CATALOG.md](CATALOG.md) — query + control sources
- [../RUNBOOK.md](../RUNBOOK.md) — setup and commands
