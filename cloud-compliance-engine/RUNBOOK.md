# Cloud Compliance Engine — Runbook

## How to run locally

1. **Environment**
   - Copy `cloud-compliance-engine/.env.example` to `cloud-compliance-engine/.env` (or use parent repo `.env`).
   - Set `DATABASE_URL`, `REDIS_URL`, and either `USE_LOCAL_STORAGE=true` + `LOCAL_STORAGE_PATH` or S3 credentials.

2. **Migrations**
   - From repo root: `alembic upgrade head` (creates `compliance` schema and tables if not already applied).

3. **Seed controls and frameworks**
   - From repo root: `PYTHONPATH=cloud-compliance-engine python -m app.scripts.seed_catalog`
   - This loads every framework in `config/catalog.yaml` (controls YAML + rules JSON) into `compliance.controls` and `compliance.framework_versions`. Required so `GET /v1/controls` and evaluation have data.

4. **Run the API**
   - From repo root with compliance app on path:
     ```bash
     PYTHONPATH=cloud-compliance-engine python -m uvicorn app.main:app --reload --app-dir cloud-compliance-engine
     ```
   - Or from `cloud-compliance-engine`: `PYTHONPATH=. python -m uvicorn app.main:app --reload`
   - API: http://localhost:8000; docs: http://localhost:8000/docs

5. **Tenant context**
   - Send header `X-Tenant-Id: <uuid>` on every request, or set `DEFAULT_TENANT_ID` in `.env` for dev.

---

## How to trigger snapshots to Postgres

Snapshots (JSON from S3 or local) are loaded into `compliance.snapshots` and `compliance.execution_snapshot_rows` by the **extract** step. You can trigger it in two ways.

### Option 1: API — extract only (ingest)

**POST /v1/snapshots/ingest**

- **Body:** `{ "snapshot_path": "<path>", "account_id": "<uuid>", "execution_job_id": "<optional>" }`
- **snapshot_path:** Full path to the snapshot JSON:
  - **S3:** `s3://<bucket>/tenant_id=.../provider=.../account_id=.../year=.../month=.../day=.../execution_id=.../result.json`
  - **Local:** e.g. `./local/snapshots/tenant_id=.../execution_id=.../result.json` (or absolute path)
- **Headers:** `X-Tenant-Id: <tenant_uuid>`
- **Response:** `{ "snapshot_id": "...", "record_count": N, "snapshot_hash": "..." }`

Example (local file):

```bash
curl -X POST "http://localhost:8000/v1/snapshots/ingest" \
  -H "X-Tenant-Id: YOUR_TENANT_UUID" \
  -H "Content-Type: application/json" \
  -d '{"snapshot_path": "./local/snapshots/tenant_id=xxx/provider=aws/account_id=yyy/year=2025/month=02/day=15/execution_id=zzz/result.json", "account_id": "YOUR_ACCOUNT_UUID"}'
```

Example (S3):

```bash
curl -X POST "http://localhost:8000/v1/snapshots/ingest" \
  -H "X-Tenant-Id: YOUR_TENANT_UUID" \
  -H "Content-Type: application/json" \
  -d '{"snapshot_path": "s3://your-bucket/tenant_id=xxx/provider=aws/account_id=yyy/year=2025/month=02/day=15/execution_id=zzz/result.json", "account_id": "YOUR_ACCOUNT_UUID"}'
```

After this, rows are in Postgres. To run compliance evaluation on this snapshot, call **POST /v1/evaluation-runs** with `"snapshot_id": "<returned snapshot_id>"`.

### Option 2: API — extract + evaluate in one call

**POST /v1/evaluation-runs**

- **Body:** `{ "s3_prefix": "<same path as above>", "account_id": "<uuid>", "framework_id": "cis_aws_v6" }`
- This runs **extract** (snapshot → Postgres) then **evaluate** (rules → control_results) in one request.
- **Response:** `{ "evaluation_run_id": "...", "snapshot_id": "..." }`

Use this when you want to ingest and evaluate in a single step.

### Option 3: Event from execution platform (optional, not yet wired)

When the Steampipe execution worker finishes a job, it can publish to Redis (`compliance:job_completed`) with `execution_job_id` and `snapshot_path`. A compliance worker would consume that message and call the extract (and then evaluate) service. To wire this:

1. In the execution worker, after writing the snapshot and setting `execution_result.snapshot_path`, publish a message to Redis with key `COMPLIANCE_QUEUE_KEY` (e.g. `compliance:job_completed`) and payload e.g. `{ "execution_job_id": "...", "snapshot_path": "...", "tenant_id": "...", "account_id": "..." }`.
2. Add a small compliance worker (or background task) that subscribes to that queue and calls `extract_snapshot_to_db` (and optionally `evaluate_snapshot`) with the payload.

Until that is implemented, use **Option 1** or **Option 2** to trigger snapshots to Postgres.

---

## How to add a new control and rule

1. **Control definition**
   - Edit `config/cis_v6_controls.yaml`: add an entry under `controls` with `control_id`, `title`, `service`, `severity`, `control_ref` (if automated), `assessment_status: Automated`.

2. **Rule (query) definition**
   - Edit `queries/cis_v6_queries.json`: add an object in `queries` with `name`, `control_id`, `control_ref`, `query_text`, `required_columns`, `pass_rule: "zero_rows"`.

3. **Seed (optional)**
   - If you have a seed script that upserts `compliance.controls` from the YAML, run it so the control appears in `GET /v1/controls`.

4. **Reload**
   - Restart the API so the in-memory rule registry reloads from `queries/cis_v6_queries.json` (or call a refresh endpoint if you add one).

---

## How to run simulate

- **POST /v1/simulate** with body: `{"snapshot_id": "<uuid>"}`.
- The engine runs the same evaluation logic but does **not** persist `control_results` or `control_state`.
- Response includes `results` with `control_id`, `status`, `rule_definition_hash`, `result_hash`, and a sample of evidence; `persisted: false`.

---

## How to interpret evidence links

- **GET /v1/control-results/{id}/evidence** returns:
  - `evidence_in_details`: list of `{ row_index, resource_id, fields }` from the control result’s `details.evidence`.
  - `evidence_resources`: normalized rows from `compliance.control_evidence_resources` (e.g. `resource_type`, `resource_id`, `payload_excerpt`).
- For a **FAIL**, each item in `evidence_resources` is an offending resource (e.g. bucket name, user ARN). Use `record_id` to join back to `compliance.execution_snapshot_rows` for the full `payload` if needed.

---

## Common failure modes

| Issue | Cause | Fix |
|-------|--------|-----|
| 400 "X-Tenant-Id header required" | No header and no `DEFAULT_TENANT_ID` | Set header or `DEFAULT_TENANT_ID` in `.env`. |
| 404 "Snapshot not found" | Wrong tenant or missing snapshot | Ensure snapshot exists and `tenant_id` matches. |
| 400 "Failed to load snapshot from path" | S3/local path wrong or no read permission | Check `s3_prefix` or local path; verify credentials and bucket. |
| Empty `GET /v1/controls` | Controls not seeded | Run seed script to load `config/cis_v6_controls.yaml` into `compliance.controls`. |
| "No rules loaded" on evaluate | `queries/cis_v6_queries.json` not found or empty | Run API from repo root or set cwd so `queries/cis_v6_queries.json` is resolvable. |

---

## Snapshot path reference

- Snapshots are read from the path stored in `execution_result.snapshot_path` (execution platform).
- Path pattern: `tenant_id={}/provider={}/account_id={}/year={}/month={}/day={}/execution_id={}/result.json` under S3 bucket or `LOCAL_STORAGE_PATH`.
- JSON shape: `{"rows": [ { ... }, ... ]}`.
