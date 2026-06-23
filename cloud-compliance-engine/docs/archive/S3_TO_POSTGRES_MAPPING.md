# Cloud Compliance Engine — S3 to Postgres Mapping

Design for mapping Steampipe snapshot data (S3) into Postgres and evaluating CIS v6 controls. Based on `data/queries.json` (49 queries, 34 CIS v6 automated) and `config/cis_v6_controls.yaml`.

---

## 0. Architecture: Modular Monolith (Same DB, Separate Schema)

**Decision:** Compliance engine is a **bounded domain** inside the same system — not a separate microservice. Use shared infrastructure with logical isolation.

| Layer | Approach |
|-------|----------|
| **PostgreSQL** | Same instance, **separate schema** `compliance` |
| **Redis** | Same instance, **separate key namespace** (e.g. `compliance:job_completed`) or Redis DB number |
| **S3** | Same bucket |

**Schema layout:**
```
public.execution_jobs
public.execution_results
public.queries
public.cloud_accounts

compliance.execution_snapshot_rows
compliance.control_results
compliance.compliance_summary
```

**Why:** Logical isolation, clear ownership, easy export to a separate DB later (dump `compliance` schema → restore elsewhere). No extra operational overhead. When job-completion events are published, use queue key `compliance:job_completed` (or similar) so compliance workers consume from a dedicated namespace.

---

## 0.1 Tenant & Account Isolation (Hybrid Design)

**Principle:** Compliance engine does not invent tenant/account identity — it inherits from the execution domain.

**Ownership chain:**
```
execution_jobs (tenant_id, account_id)
    ↓
execution_results (execution_job_id, snapshot_path)
    ↓
compliance.execution_snapshot_rows
compliance.control_results
compliance.control_evidence_resources
compliance.compliance_summary
```

**Hybrid approach (recommended for multi-tenant SaaS):**

| Approach | What we do |
|----------|------------|
| **FK** | Store `execution_job_id` — single source of truth, referential integrity |
| **Denormalize** | Store `tenant_id`, `account_id` in compliance tables — fast filtering, simpler APIs, no JOIN for isolation |

**Why both?**
- `execution_job_id` → correct ownership chain, audit trail
- `tenant_id`, `account_id` → `WHERE tenant_id = ?` without JOIN, RLS-friendly, index-friendly

**Propagation:** At extract time, read `tenant_id`, `account_id` from `execution_jobs` (via `execution_results.execution_job_id`) and write into compliance tables. No duplication of logic — one write path.

**Do NOT:** Store only `execution_job_id` and require JOIN for every tenant-filtered query. That hurts API latency and RLS patterns.

---

## 1. Source: S3 Snapshot Structure

**Path pattern** (from Steampipe execution platform):
```
tenant_id={tenant_id}/provider={provider}/account_id={account_id}/
year={YYYY}/month={MM}/day={DD}/execution_id={execution_job_id}/result.json
```

**JSON structure** (from `SnapshotService.persist_snapshot`):
```json
{
  "rows": [
    {"name": "bucket1", "region": "us-east-1", "versioning_enabled": false},
    {"name": "bucket2", "region": "us-east-1", "versioning_enabled": true}
  ]
}
```

- Steampipe `--output=json` returns an array of row objects.
- Worker wraps as `{"rows": output}` when needed.
- Each row is a flat JSON object; keys = column names from the query.

---

## 2. Execution Platform Tables (Steampipe Repo — `public` schema)

| Table | Schema | Key columns | Purpose |
|-------|--------|-------------|---------|
| execution_jobs | public | id, tenant_id, account_id, query_id, status | Job lifecycle |
| execution_results | public | execution_job_id, snapshot_path, row_count, status | Result + S3 path |
| queries | public | id, name, query_text, extra_metadata | Query metadata |
| cloud_accounts | public | id, tenant_id, provider, account_id | Account info |

**Query metadata** (from `queries.extra_metadata` for compliance):
```json
{
  "category": "compliance",
  "framework": "CIS AWS Foundations Benchmark v6.0.0",
  "control_id": "3.1.4",
  "control_ref": "s3-public-access",
  "required_columns": ["name", "block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"],
  "pass_rule": "zero_rows"
}
```

---

## 3. Compliance Engine: Phase 1 — Extract (S3 → Postgres)

### 3.1 Trigger

- **Event:** Execution platform completes job → `execution_result.snapshot_path` set. Publish to Redis with **separate namespace**: e.g. key/queue `compliance:job_completed` (or use Redis DB 2 for compliance workers).
- **Filter:** Only compliance queries (`extra_metadata.category == "compliance"` and `framework` set).
- **Input:** `execution_job_id`, `snapshot_path`, `tenant_id`, `account_id`, `query_id`, `run_at` (payload can be minimal; worker can JOIN with `public.execution_results` and `public.queries`).

### 3.2 Extract Table: `compliance.execution_snapshot_rows`

**Storage choice:** JSONB for `row_data` — no relational columns per snapshot field, no ETL tools, no dynamic tables. Flexible for different queries; supports GIN indexing; no migration when snapshot structure changes.

```sql
CREATE SCHEMA IF NOT EXISTS compliance;

CREATE TABLE compliance.execution_snapshot_rows (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  execution_job_id  UUID NOT NULL REFERENCES public.execution_jobs(id) ON DELETE CASCADE,
  tenant_id         UUID NOT NULL,  -- denormalized from execution_jobs for hybrid filtering
  account_id        UUID NOT NULL,  -- denormalized from execution_jobs for hybrid filtering
  query_id          UUID NOT NULL,
  run_at            TIMESTAMPTZ NOT NULL,
  row_index         INT NOT NULL,
  row_data          JSONB NOT NULL,
  snapshot_hash     TEXT,
  created_at        TIMESTAMPTZ DEFAULT now(),
  UNIQUE(execution_job_id, row_index)
);

CREATE INDEX idx_snapshot_rows_exec ON compliance.execution_snapshot_rows(execution_job_id);
CREATE INDEX idx_snapshot_rows_tenant_run ON compliance.execution_snapshot_rows(tenant_id, run_at);
CREATE INDEX idx_snapshot_rows_query ON compliance.execution_snapshot_rows(query_id);
CREATE INDEX idx_snapshot_rows_gin ON compliance.execution_snapshot_rows USING GIN (row_data);
```

**Explicitly do NOT:** Auto-generate relational columns per snapshot field, use ETL tools (Airbyte, etc.), create dynamic SQL tables per query, or use Pandas → fixed-schema ORM bulk insert.

**snapshot_hash (deterministic auditability):** Compute from normalized JSON (sorted keys) so identical data produces the same hash. Use before insert:

```python
import hashlib
import json

def compute_snapshot_hash(row: dict) -> str:
    normalized = json.dumps(row, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(normalized.encode()).hexdigest()
```

### 3.3 Extract Logic

```
1. Resolve execution_job → tenant_id, account_id, query_id, run_at (from execution_jobs)
2. GET snapshot_path from S3 (execution_results.snapshot_path)
3. Parse JSON → data["rows"] or data (if array)
4. For each row in rows:
   INSERT INTO compliance.execution_snapshot_rows (
     execution_job_id, tenant_id, account_id, query_id, run_at,
     row_index, row_data, snapshot_hash
   ) VALUES (
     :execution_job_id, :tenant_id, :account_id, :query_id, :run_at,
     :i, :row::jsonb, :snapshot_hash  -- computed via compute_snapshot_hash(row)
   )
   ON CONFLICT (execution_job_id, row_index) DO UPDATE SET row_data = EXCLUDED.row_data, snapshot_hash = EXCLUDED.snapshot_hash
5. Idempotent: upsert by (execution_job_id, row_index)
```

**Python flow (boto3 + SQLAlchemy, no ETL):**
```python
def load_snapshot_to_db(snapshot_path: str, execution_job_id: str, db: Session):
    job = db.query(ExecutionJob).get(execution_job_id)
    tenant_id, account_id = job.tenant_id, job.account_id
    query_id, run_at = job.query_id, job.started_at or job.finished_at

    s3 = boto3.client("s3")
    bucket, key = parse_s3_path(snapshot_path)
    content = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    rows = json.loads(content).get("rows", json.loads(content))

    objects = [
        ExecutionSnapshotRow(
            execution_job_id=execution_job_id,
            tenant_id=tenant_id,
            account_id=account_id,
            query_id=query_id,
            run_at=run_at,
            row_index=i,
            row_data=row,
            snapshot_hash=compute_snapshot_hash(row),
        )
        for i, row in enumerate(rows)
    ]
    db.bulk_save_objects(objects)
    db.commit()
```

### 3.4 Row Data Shape (per query)

Each `row_data` JSONB mirrors the query SELECT. Examples:

| Query | row_data keys |
|-------|---------------|
| cis_3_1_4_s3_public_access | name, block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets |
| cis_2_3_iam_root_access_keys | account_id, account_access_keys_present |
| cis_3_2_3_rds_public | db_instance_identifier, publicly_accessible |
| cis_6_2_nacl_admin_ports | network_acl_id, region, account_id |

---

## 4. Compliance Engine: Phase 2 — Apply Rules

### 4.1 Rule Engine Input

For each `execution_job_id` with compliance query:

- **From:** `compliance.execution_snapshot_rows` (filter by execution_job_id)
- **From:** `public.queries.extra_metadata` (framework, control_id, control_ref, pass_rule, required_columns)
- **From:** `config/cis_v6_controls.yaml` (severity, title, remediation) — optional enrichment

### 4.2 Pass Rule: `zero_rows`

```python
# zero_rows: 0 rows returned = PASS, any rows = FAIL
rows = fetch_snapshot_rows(execution_job_id)
status = "pass" if len(rows) == 0 else "fail"
```

For CIS v6, all 34 automated controls use `pass_rule: "zero_rows"`:
- Query returns **violations** (e.g. buckets without block public access).
- 0 rows = no violations = PASS.
- 1+ rows = violations = FAIL.

### 4.3 Evidence Builder

From `row_data` + `required_columns`:

```python
evidence = []
evidence_resources = []
for row in rows:
    resource_id = (row.row_data.get("name") or row.row_data.get("instance_id")
                   or row.row_data.get("account_id") or row.row_data.get("region") or str(row.row_index))
    key_field = "name" if "name" in row.row_data else "db_instance_identifier" if "db_instance_identifier" in row.row_data else "account_id"
    key_value = row.row_data.get(key_field, resource_id)

    evidence.append({
        "row_index": row.row_index,
        "resource_id": resource_id,
        "fields": {k: row.row_data.get(k) for k in required_columns if k in row.row_data}
    })
    evidence_resources.append({
        "resource_type": _infer_resource_type(query_metadata),  # from control_ref or query
        "resource_id": resource_id,
        "key_field": key_field,
        "key_value": key_value,
        "row_index": row.row_index,
    })
summary = f"{len(rows)} violation(s) found"  # e.g. "3 buckets with public access not blocked"
```

After inserting `control_results`, bulk insert into `control_evidence_resources` (one row per evidence item).

### 4.4 Control Results Table: `compliance.control_results`

`tenant_id`, `account_id` are denormalized (hybrid design) for fast tenant-filtered queries.

```sql
CREATE TABLE compliance.control_results (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL,  -- denormalized for hybrid filtering
  account_id          UUID NOT NULL,  -- denormalized for hybrid filtering
  execution_job_id    UUID NOT NULL REFERENCES public.execution_jobs(id) ON DELETE CASCADE,
  framework           TEXT NOT NULL,
  framework_version   TEXT,
  control_id          TEXT NOT NULL,
  control_ref         TEXT NOT NULL,
  status              TEXT NOT NULL,  -- 'pass' | 'fail'
  severity            TEXT,
  evidence            JSONB,
  summary             TEXT,
  evaluated_at        TIMESTAMPTZ DEFAULT now(),
  run_at              TIMESTAMPTZ NOT NULL,
  status_changed      BOOLEAN DEFAULT false,
  previous_status     TEXT,
  UNIQUE(execution_job_id, framework, control_ref)
);

CREATE INDEX idx_control_results_tenant ON compliance.control_results(tenant_id);
CREATE INDEX idx_control_results_account ON compliance.control_results(account_id);
CREATE INDEX idx_control_results_account_framework ON compliance.control_results(account_id, framework);
CREATE INDEX idx_control_results_status ON compliance.control_results(status) WHERE status = 'fail';
```

### 4.5 Control Evidence Resources (Column-wise for Fast Search)

Normalized table for dashboard queries and resource-level search. Populated from `control_results.evidence` when writing control results.

```sql
CREATE TABLE compliance.control_evidence_resources (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  control_result_id     UUID NOT NULL REFERENCES compliance.control_results(id) ON DELETE CASCADE,
  tenant_id             UUID NOT NULL,
  account_id            UUID NOT NULL,
  resource_type         TEXT NOT NULL,   -- e.g. 's3_bucket', 'iam_user', 'rds_instance'
  resource_id           TEXT NOT NULL,   -- e.g. bucket name, user ARN, instance ID
  key_field             TEXT NOT NULL,   -- primary identifier column name (e.g. 'name', 'db_instance_identifier')
  key_value             TEXT NOT NULL,   -- value of key_field
  row_index             INT,
  created_at            TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_evidence_resources_control ON compliance.control_evidence_resources(control_result_id);
CREATE INDEX idx_evidence_resources_tenant ON compliance.control_evidence_resources(tenant_id);
CREATE INDEX idx_evidence_resources_account ON compliance.control_evidence_resources(account_id);
CREATE INDEX idx_evidence_resources_resource ON compliance.control_evidence_resources(resource_type, resource_id);
CREATE INDEX idx_evidence_resources_key ON compliance.control_evidence_resources(key_field, key_value);
```

**Storage strategy summary:**

| Table | Storage | Purpose |
|-------|---------|---------|
| execution_snapshot_rows | JSONB whole row | Audit, replay, drift detection |
| control_results.evidence | JSONB structured | Full evidence (resource_id, fields, row_index) |
| control_evidence_resources | Column-wise | Fast search, dashboards, resource-level queries |

---

## 5. Compliance Summary: `compliance.compliance_summary`

`tenant_id`, `account_id` denormalized for hybrid filtering (same pattern as execution_snapshot_rows, control_results).

```sql
CREATE TABLE compliance.compliance_summary (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                   UUID NOT NULL,
  account_id                  UUID NOT NULL,
  framework                   TEXT NOT NULL,
  period_start                TIMESTAMPTZ NOT NULL,
  period_end                  TIMESTAMPTZ NOT NULL,
  total_controls_evaluated    INT NOT NULL,
  passed_count                INT NOT NULL,
  failed_count                INT NOT NULL,
  pass_percentage             NUMERIC(5,2),
  severity_weighted_score     NUMERIC,
  last_evaluated_at           TIMESTAMPTZ NOT NULL
);
```

---

## 6. Query → Control Mapping (CIS v6)

| control_ref | control_id | Query name | required_columns (sample) |
|-------------|------------|------------|---------------------------|
| iam-root-access-keys | 2.3 | cis_2_3_iam_root_access_keys | account_id, account_access_keys_present |
| iam-root-mfa | 2.4 | cis_2_4_iam_root_mfa | account_id, account_mfa_enabled, account_password_present |
| iam-password-min-length | 2.7 | cis_2_7_iam_password_min_length | minimum_password_length |
| iam-password-reuse | 2.8 | cis_2_8_iam_password_reuse | password_reuse_prevention |
| iam-user-mfa | 2.9 | cis_2_9_iam_user_mfa | name, user_id, mfa_enabled |
| s3-deny-http | 3.1.1 | cis_3_1_1_s3_deny_http | name, region, bucket_policy |
| s3-public-access | 3.1.4 | cis_3_1_4_s3_public_access | name, block_public_acls, ... |
| rds-encryption | 3.2.1 | cis_3_2_1_rds_encryption | db_instance_identifier, storage_encrypted |
| rds-public | 3.2.3 | cis_3_2_3_rds_public | db_instance_identifier, publicly_accessible |
| ... | ... | ... | (see data/queries.json) |

Full mapping: `config/cis_v6_controls.yaml` for control_id + severity; `query.extra_metadata.control_ref` links query to control.

---

## 7. End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 1: EXECUTION (Steampipe platform)                                      │
│  Worker runs query → Steampipe JSON → S3 persist snapshot_path               │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ event: job done
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 2: EXTRACT (Compliance Engine Phase 1)                                  │
│  GET S3 result.json → parse rows → INSERT compliance.execution_snapshot_rows  │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 3: EVALUATE (Compliance Engine Phase 2)                                 │
│  READ execution_snapshot_rows → pass_rule (zero_rows) → evidence             │
│  → INSERT control_results + control_evidence_resources                       │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STEP 4: AGGREGATE                                                            │
│  compliance.control_results → compliance.compliance_summary (pass %, score)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Implementation Checklist

- [ ] Create `compliance` schema (same PostgreSQL instance as `public`)
- [ ] `compliance.execution_snapshot_rows` migration (with snapshot_hash)
- [ ] `compliance.control_results` migration
- [ ] `compliance.control_evidence_resources` migration
- [ ] `compliance.compliance_summary` migration
- [ ] Extract service: S3 → compliance.execution_snapshot_rows
- [ ] Rule engine: zero_rows handler
- [ ] Evidence builder from row_data + required_columns
- [ ] Populate control_evidence_resources when writing control_results
- [ ] Trigger: Redis queue `compliance:job_completed` (or dedicated Redis DB) on job completion
- [ ] `config/cis_v6_controls.yaml` loader for severity
- [ ] API: GET /control_results, GET /compliance_summary (query `compliance.*` tables)

---

## 9. References

- `data/queries.json` — 49 queries, 34 CIS v6 with control_id, control_ref, pass_rule, required_columns
- `config/cis_v6_controls.yaml` — CIS v6 control definitions, severity, remediation
- `src/services/snapshot.py` — S3 persist path and JSON structure
- `docs/ARCHITECTURE_EXTRACT_VS_ENGINE.md` — Extract-first design rationale

---

## 10. Future: Extracting Compliance to a Separate DB

If you later need a dedicated compliance database (scale, team, or product boundary):

1. Dump: `pg_dump --schema=compliance` (or export `compliance` schema only).
2. Restore into a new PostgreSQL instance.
3. Point compliance service at new `DATABASE_URL`.
4. Event payload may need to carry full context (or compliance service reads from an API/replica of `public`). No schema change required — separation was prepared by using `compliance` schema from day one.
