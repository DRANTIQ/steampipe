# Cloud Compliance Engine — Implementation Prompt

**Single source of truth for building the full Cloud Compliance Engine end-to-end.**

**Data source:** The compliance engine only reads **snapshot JSON from S3** (or local path). It does not run Steampipe or any query engine. Snapshots may be produced by a separate execution platform (e.g. Steampipe); this service just consumes the stored JSON and evaluates rules.

Read this document first. Then read: `DESIGN.md`, `docs/S3_TO_POSTGRES_MAPPING.md`, `docs/ARCHITECTURE.md`, `config/cis_v6_controls.yaml`, `queries/cis_v6_queries.json`.

---

## 0. Quick Reference

### 0.1 Folder Layout (Target)

```
cloud-compliance-engine/
├── app/                          # FastAPI service
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── v1/
│   │   │   ├── evaluation_runs.py
│   │   │   ├── control_results.py
│   │   │   ├── controls.py
│   │   │   ├── control_status.py
│   │   │   └── simulate.py
│   │   └── deps.py               # tenant context, DB session
│   ├── services/
│   │   ├── extract.py            # S3 → snapshot rows
│   │   ├── evaluate.py           # rule engine
│   │   ├── hash_utils.py          # canonical JSON, record_hash, snapshot_hash
│   │   └── rule_registry.py      # rule definitions, safe execution
│   ├── models/                   # SQLAlchemy (or Pydantic for API)
│   └── schemas/                  # Pydantic request/response
├── migrations/                   # Alembic
├── tests/
│   ├── unit/
│   │   ├── test_hash.py
│   │   ├── test_parsers.py
│   │   └── test_rule_engine.py
│   ├── integration/
│   │   └── test_pipeline.py
│   └── fixtures/
│       ├── sample_snapshot.json
│       └── expected_control_results.json
├── config/
│   └── cis_v6_controls.yaml
├── queries/
│   └── cis_v6_queries.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── S3_TO_POSTGRES_MAPPING.md
│   ├── DB_SCHEMA.md
│   └── RUNBOOK.md
├── docker-compose.yml
├── Makefile
└── RUNBOOK.md
```

### 0.2 Key File References

| Purpose | Path |
|---------|------|
| Control definitions | `config/cis_v6_controls.yaml` |
| Query catalog (CIS v6) | `queries/cis_v6_queries.json` |
| Parent queries (49 total) | `../data/queries.json` (Steampipe platform) |
| S3 path pattern | `tenant_id={}/provider={}/account_id={}/year={}/month={}/day={}/execution_id={}/result.json` |
| Snapshot JSON shape | `{"rows": [{...}, {...}]}` |
| SnapshotService | `../src/services/snapshot.py` (parent repo) |

---

## 1. Hard Requirements

### 1.1 Determinism & Auditability

| Requirement | Implementation |
|-------------|----------------|
| **record_hash** | SHA256 of canonical JSON (sorted keys, no whitespace) per extracted row |
| **snapshot_hash** | Deterministic aggregation of record_hashes (ordered set) or Merkle-like |
| **rule_definition_hash** | SHA256 of canonical rule JSON (control_ref, pass_rule, required_columns, etc.) |
| **evaluation_runs** | Pin exact `rule_version_id` + `framework_version_id` |
| **control_results** | Chain: `prev_result_hash`, `result_hash` for tamper detection within a run |

**Canonical JSON:**
```python
import hashlib
import json

def canonical_hash(obj: dict) -> str:
    normalized = json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()
```

### 1.2 Immutability & Idempotency

| Requirement | Implementation |
|-------------|----------------|
| Extracted data | Append-only per snapshot; no updates; only new snapshots |
| Evaluation writes | Idempotent: re-run same `(snapshot_id, rule_version_id)` → no duplicate results |
| Jobs | Retry-safe; use `ON CONFLICT DO NOTHING` or `UNIQUE` + upsert |

### 1.3 Explainability

| Requirement | Implementation |
|-------------|----------------|
| FAIL | Must link to ≥1 evidence via `control_evidence_resources` |
| PASS | May link evidence optionally |
| UNKNOWN | Must include `message` (e.g. "missing evidence source") |

### 1.4 Security / Multi-tenant

| Requirement | Implementation |
|-------------|----------------|
| Scoping | Every row: `tenant_id` (UUID) + `account_id` |
| RLS | Enable Postgres RLS; policy: `tenant_id = current_setting('app.tenant_id')::uuid` |
| API | Require tenant context: `X-Tenant-Id` header or JWT claim; validate UUID |

### 1.5 Safe Query Execution

**DO NOT** execute arbitrary raw SQL from config.

**Option A (recommended):** DSL compiled to parameterized SQL
- Define: `target_source`, `record_type`, `filters` (jsonpath-like), `group_by`, `aggregation`, `pass_condition`, `evidence_selector`
- Compile → parameterized SQL against `execution_snapshot_rows` (JSONB)

**Option B:** Validated SQL templates
- Whitelist tables only: `execution_snapshot_rows` (or normalized views)
- No semicolons, DDL, DML, COPY, pg_sleep, unsafe functions
- Parameters via bindvars only

**Never** interpolate user input into SQL.

### 1.6 Performance

| Requirement | Implementation |
|-------------|----------------|
| Partitioning | Large append-only tables: by `tenant_id` + time (`snapshot_time` / `run_time`) |
| Indexes | Hot paths: `run_id`, `control_id`, latest state, evidence retrieval |
| Latest status | Fast endpoint backed by `control_state` or materialized view |

---

## 2. Stack

- **Python 3.11+**, **FastAPI**, **SQLAlchemy** (sync or async)
- **PostgreSQL 15+**
- **Alembic** migrations
- **Docker Compose** (Postgres, optional MinIO for S3-compatible local)
- **pytest** for tests

Parent repo (Steampipe platform) uses same DB; compliance uses **separate schema** `compliance`.

---

## 3. Domain Model (Tables)

All compliance tables live in schema `compliance`. Parent tables in `public`: `execution_jobs`, `execution_results`, `queries`, `cloud_accounts`.

### 3.1 Core Catalogs

```sql
-- controls: first-class control definitions
CREATE TABLE compliance.controls (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  control_id        TEXT NOT NULL,        -- e.g. "2.3", "3.1.4"
  framework_id      TEXT NOT NULL,        -- e.g. "cis_aws_v6"
  title             TEXT,
  description       TEXT,
  severity          TEXT NOT NULL,        -- Critical | High | Medium | Low
  rationale         TEXT,
  remediation       TEXT,
  references        JSONB,
  tags              JSONB,
  enabled           BOOLEAN DEFAULT true,
  UNIQUE(framework_id, control_id)
);

-- framework_versions: framework version metadata
CREATE TABLE compliance.framework_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_id  TEXT NOT NULL,
  version_name  TEXT NOT NULL,
  published_at  TIMESTAMPTZ,
  source_uri    TEXT,
  hash          VARCHAR(64),
  UNIQUE(framework_id, version_name)
);

-- rule_versions: rule definition versions
CREATE TABLE compliance.rule_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_id  TEXT NOT NULL,
  version_name  TEXT NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT now(),
  hash          VARCHAR(64) NOT NULL,     -- rule_definition_hash
  notes         TEXT,
  UNIQUE(framework_id, version_name)
);
```

### 3.2 Snapshots & Runs

```sql
-- snapshots: one per ingestion
CREATE TABLE compliance.snapshots (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL,
  account_id      UUID NOT NULL,
  snapshot_time   TIMESTAMPTZ NOT NULL,
  sources         TEXT[],                 -- ['steampipe'] or ['cloudtrail','config']
  s3_prefix       TEXT,
  snapshot_hash   VARCHAR(64) NOT NULL,
  record_count    INT NOT NULL DEFAULT 0,
  execution_job_id UUID,                   -- FK to public.execution_jobs (when from Steampipe)
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- evaluation_runs: evaluation lifecycle
CREATE TABLE compliance.evaluation_runs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             UUID NOT NULL,
  account_id            UUID NOT NULL,
  regions               TEXT[],
  framework_version_id  UUID REFERENCES compliance.framework_versions(id),
  rule_version_id       UUID REFERENCES compliance.rule_versions(id),
  status                TEXT NOT NULL,     -- queued | running | succeeded | failed
  started_at            TIMESTAMPTZ,
  finished_at           TIMESTAMPTZ,
  created_at            TIMESTAMPTZ DEFAULT now(),
  snapshot_id           UUID REFERENCES compliance.snapshots(id),
  idempotency_key       TEXT UNIQUE,
  run_hash              VARCHAR(64)
);
```

### 3.3 Extract Storage (Append-only)

```sql
CREATE TABLE compliance.execution_snapshot_rows (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL,
  account_id        UUID NOT NULL,
  snapshot_id       UUID NOT NULL REFERENCES compliance.snapshots(id),
  source            TEXT NOT NULL,         -- steampipe | cloudtrail | config | securityhub
  record_type       TEXT NOT NULL,         -- e.g. steampipe_row, cloudtrail_event, config_resource
  event_time        TIMESTAMPTZ,
  region            TEXT,
  natural_key       TEXT,
  record_hash       VARCHAR(64) NOT NULL,
  payload           JSONB NOT NULL,
  created_at        TIMESTAMPTZ DEFAULT now(),
  UNIQUE(snapshot_id, record_hash)
);

CREATE INDEX idx_snapshot_rows_snapshot ON compliance.execution_snapshot_rows(snapshot_id);
CREATE INDEX idx_snapshot_rows_source ON compliance.execution_snapshot_rows(snapshot_id, source, record_type);
CREATE INDEX idx_snapshot_rows_tenant_time ON compliance.execution_snapshot_rows(tenant_id, created_at);
CREATE INDEX idx_snapshot_rows_gin ON compliance.execution_snapshot_rows USING GIN (payload);
```

**Steampipe mapping:** `source='steampipe'`, `record_type='steampipe_row'`, `payload` = full row JSON, `record_hash` = canonical_hash(row).

**Bridge from existing S3_TO_POSTGRES_MAPPING:** Existing docs use `execution_job_id` directly on `execution_snapshot_rows`. New schema uses `snapshot_id` → `snapshots`. Flow: (1) Create `snapshots` row with `execution_job_id` when from Steampipe; (2) Extract inserts `execution_snapshot_rows` with `snapshot_id`. Snapshot links to execution platform for traceability.

### 3.4 Evaluation Output

```sql
CREATE TABLE compliance.control_results (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             UUID NOT NULL,
  account_id            UUID NOT NULL,
  evaluation_run_id     UUID NOT NULL REFERENCES compliance.evaluation_runs(id),
  snapshot_id           UUID NOT NULL REFERENCES compliance.snapshots(id),
  framework_id          TEXT NOT NULL,
  control_id            TEXT NOT NULL,
  status                TEXT NOT NULL,     -- PASS | FAIL | UNKNOWN
  severity              TEXT,
  score_delta           NUMERIC,
  message               TEXT,
  rule_definition_hash   VARCHAR(64) NOT NULL,
  snapshot_hash         VARCHAR(64) NOT NULL,
  evaluated_at          TIMESTAMPTZ DEFAULT now(),
  result_hash           VARCHAR(64) NOT NULL,
  prev_result_hash      VARCHAR(64),
  details               JSONB,
  UNIQUE(evaluation_run_id, control_id)
);

CREATE TABLE compliance.control_evidence_resources (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL,
  account_id        UUID NOT NULL,
  control_result_id UUID NOT NULL REFERENCES compliance.control_results(id) ON DELETE CASCADE,
  source            TEXT NOT NULL,
  record_id         UUID,                 -- execution_snapshot_rows.id or record_hash
  resource_type     TEXT NOT NULL,
  resource_id       TEXT NOT NULL,
  evidence_locator  TEXT,                 -- s3 key / pointer
  evidence_hash     VARCHAR(64),
  event_time        TIMESTAMPTZ,
  region            TEXT,
  payload_excerpt   JSONB,
  created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_evidence_control ON compliance.control_evidence_resources(control_result_id);
CREATE INDEX idx_evidence_resource ON compliance.control_evidence_resources(resource_type, resource_id);
```

### 3.5 Latest Cache & Summaries

```sql
CREATE TABLE compliance.control_state (
  tenant_id               UUID NOT NULL,
  account_id               UUID NOT NULL,
  framework_id             TEXT NOT NULL,
  control_id               TEXT NOT NULL,
  latest_control_result_id  UUID REFERENCES compliance.control_results(id),
  latest_status            TEXT NOT NULL,
  last_evaluated_at        TIMESTAMPTZ NOT NULL,
  last_snapshot_id         UUID,
  updated_at               TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (tenant_id, account_id, framework_id, control_id)
);

CREATE TABLE compliance.compliance_summary (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id               UUID NOT NULL,
  account_id              UUID NOT NULL,
  framework_id            TEXT NOT NULL,
  evaluation_run_id       UUID REFERENCES compliance.evaluation_runs(id),
  pass_count              INT NOT NULL,
  fail_count              INT NOT NULL,
  unknown_count           INT NOT NULL DEFAULT 0,
  score_total             NUMERIC,
  severity_breakdown      JSONB,
  created_at              TIMESTAMPTZ DEFAULT now()
);
```

### 3.6 Jobs & Metrics

```sql
CREATE TABLE compliance.jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL,
  job_type            TEXT NOT NULL,     -- extract | evaluate | summarize
  status              TEXT NOT NULL,
  evaluation_run_id   UUID,
  snapshot_id         UUID,
  attempt             INT DEFAULT 1,
  last_error          TEXT,
  created_at          TIMESTAMPTZ DEFAULT now(),
  updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE compliance.control_metrics (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL,
  evaluation_run_id   UUID NOT NULL,
  control_id          TEXT NOT NULL,
  query_time_ms       INT,
  rows_scanned        INT,
  evidence_count      INT,
  notes               JSONB,
  created_at          TIMESTAMPTZ DEFAULT now()
);
```

### 3.7 RLS

```sql
ALTER TABLE compliance.snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance.execution_snapshot_rows ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance.evaluation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance.control_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance.control_evidence_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance.control_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance.compliance_summary ENABLE ROW LEVEL SECURITY;

-- Policy (repeat for each table):
CREATE POLICY tenant_isolation ON compliance.snapshots
  USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

API sets `SET LOCAL app.tenant_id = '<tenant_uuid>'` per request.

---

## 4. Config & Rule Definitions

### 4.1 Load Control Catalog

- **Source:** `config/cis_v6_controls.yaml`
- **Structure:** `framework`, `framework_version`, `controls[]` with `control_id`, `title`, `service`, `severity`, `control_ref`, `assessment_status`
- **Action:** Parse → upsert into `compliance.controls`, `compliance.framework_versions`

### 4.2 Load Query Catalog

- **Source:** `queries/cis_v6_queries.json` (or `../data/queries.json` for compliance queries)
- **Structure:** `name`, `control_id`, `control_ref`, `query_text`, `required_columns`, `pass_rule`
- **Action:** Build `rule_versions`; compute `rule_definition_hash` for each (canonical JSON of rule)

### 4.3 Rule Registry

- Parse config into internal models
- Compute `rule_definition_hash` for each rule (stable, canonical)
- Store in `rule_versions`; link to controls via `control_ref` → `control_id`

### 4.4 Safe Execution

- **Option A:** DSL → parameterized SQL against `execution_snapshot_rows` (JSONB `payload`)
- **Option B:** Validate SQL templates; whitelist tables; bindvars only

For CIS v6: `pass_rule: zero_rows` → no raw SQL; count rows from `execution_snapshot_rows` where `payload` matches filter. No user SQL execution.

### 4.5 Evidence Selection

- Each rule defines how to select evidence rows for FAIL (e.g. top N offending resources)
- Store in `control_evidence_resources` with `record_id`, `resource_type`, `resource_id`, `payload_excerpt`

---

## 5. Extract Phase (S3 → Snapshot Rows)

### 5.1 Trigger

- **Steampipe path:** Execution platform completes job → `execution_results.snapshot_path` set → publish to `compliance:job_completed` (Redis)
- **S3 prefix path:** POST `/v1/evaluation-runs` with `s3_prefix` → create snapshot + extract job

### 5.2 Steampipe Snapshot Format

- **Path:** `s3://bucket/tenant_id={}/provider={}/account_id={}/year={}/month={}/day={}/execution_id={}/result.json`
- **JSON:** `{"rows": [{"name": "bucket1", "region": "us-east-1", ...}, ...]}`
- **Source:** `SnapshotService.persist_snapshot` in `../src/services/snapshot.py`

### 5.3 Extract Steps

1. Create `snapshots` row (tenant_id, account_id, snapshot_time, sources=['steampipe'], s3_prefix, execution_job_id)
2. Fetch JSON from S3 (or local path)
3. For each row in `data["rows"]`:
   - Normalize: `source='steampipe'`, `record_type='steampipe_row'`
   - Compute `record_hash = canonical_hash(row)`
   - Insert into `execution_snapshot_rows` with `ON CONFLICT (snapshot_id, record_hash) DO NOTHING`
4. Compute `snapshot_hash` = ordered aggregation of record_hashes (deterministic)
5. Update `snapshots.snapshot_hash`, `snapshots.record_count`
6. Mark extract job succeeded

### 5.4 Pluggable Parsers (Future)

- CloudTrail: JSON lines or JSON arrays
- AWS Config: configuration items
- SecurityHub: findings exports

Provide parsers per source with unit tests and fixtures.

---

## 6. Evaluate Phase (Snapshot → Control Results)

### 6.1 Steps

1. Create `evaluation_run` (pin `framework_version_id`, `rule_version_id`)
2. Verify snapshot exists and has `snapshot_hash`
3. For each enabled control in framework:
   - Execute rule safely (zero_rows: count rows from `execution_snapshot_rows` where snapshot_id = X and payload matches)
   - Determine status: PASS | FAIL | UNKNOWN
   - Create `control_results` row (idempotent: UNIQUE(evaluation_run_id, control_id))
   - Insert evidence rows for FAIL (and optionally PASS)
   - Compute `result_hash`, `prev_result_hash` (chain)
   - Write `control_metrics`
4. Build `compliance_summary` for run
5. Upsert `control_state` for latest
6. Mark `evaluation_run` succeeded

### 6.2 UNKNOWN Logic

- If required source/record_type missing in snapshot → UNKNOWN with message "missing evidence source"

### 6.3 zero_rows Rule (CIS v6)

- Query returns violations (e.g. buckets without block public access)
- 0 rows = PASS
- 1+ rows = FAIL
- Evidence: `required_columns` from `payload`; resource_id from `name` or `db_instance_identifier` or `account_id`

---

## 7. API (FastAPI)

### 7.1 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/evaluation-runs` | Body: `{account_id, snapshot_id?, s3_prefix?, framework_id, rule_version?}`. If no snapshot_id, create snapshot + extract then evaluate. Return evaluation_run_id |
| GET | `/v1/evaluation-runs/{id}` | Run metadata and status |
| GET | `/v1/controls` | Query: `framework_id`, `severity`, `enabled`. Control catalog |
| GET | `/v1/control-results` | Query: `run_id`. List results (control_id, status, severity, message, evaluated_at) |
| GET | `/v1/control-results/{id}/evidence` | Evidence links |
| GET | `/v1/control-status/latest` | Query: `account_id`, `framework_id`. Latest status per control from `control_state` |
| POST | `/v1/simulate` | Body: `{snapshot_id, proposed_rules? or rule_version_id?}`. Run evaluation in-memory; DO NOT persist. Return same shape as real results including hashes |

### 7.2 Auth / Tenant

- Local dev: `X-Tenant-Id` header → `SET LOCAL app.tenant_id = '<uuid>'`
- Validate tenant_id is UUID
- Every query tenant-scoped

---

## 8. Local Dev + Runbook

### 8.1 Docker Compose

```yaml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: steampipe
      POSTGRES_USER: steampipe
      POSTGRES_PASSWORD: steampipe
    ports:
      - "5432:5432"
  minio:  # optional, for S3-compatible local
    image: minio/minio
    command: server /data
    ports:
      - "9000:9000"
```

### 8.2 Makefile

```
up          - docker-compose up -d
migrate     - alembic upgrade head
seed        - load controls + rules from config
extract_sample - load fixtures into execution_snapshot_rows
eval_sample - run evaluation on sample
test        - pytest
```

### 8.3 RUNBOOK.md

- How to run locally
- How to add a new control and rule
- How to run simulate
- How to interpret evidence links
- Common failure modes

---

## 9. Testing

| Test | Description |
|------|-------------|
| Canonical JSON hashing | Same object → same hash; different → different |
| Parser tests | Each evidence source (Steampipe, future CloudTrail/Config) |
| Golden fixture | sample_snapshot.json → expected control_results |
| Idempotency | Re-run same (snapshot_id, rule_version_id) → no duplicate results |
| RLS | Different tenant_id cannot read rows |
| Simulate | Returns results; DB unchanged |

---

## 10. Implementation Order

**Step 1: Folder layout + migrations**
- Create `app/`, `migrations/`, `tests/`, `fixtures/`
- Alembic init; create `compliance` schema + all tables from §3
- RLS policies

**Step 2: Hash utilities**
- `canonical_hash(obj)`, `record_hash(row)`, `snapshot_hash(record_hashes)`, `rule_definition_hash(rule)`

**Step 3: Config loader**
- Load `config/cis_v6_controls.yaml` → `controls`, `framework_versions`
- Load `queries/cis_v6_queries.json` → `rule_versions` with hash

**Step 4: Extract service**
- S3 (or local) → parse `{"rows": [...]}` → `snapshots` + `execution_snapshot_rows`
- record_hash per row; snapshot_hash aggregation

**Step 5: Rule engine**
- zero_rows handler
- Evidence builder
- Safe execution (no raw SQL from config)

**Step 6: Evaluate service**
- Create evaluation_run → for each control → execute rule → control_results + control_evidence_resources
- result_hash chain; control_state upsert; compliance_summary

**Step 7: API**
- FastAPI app; X-Tenant-Id dep; all endpoints from §7

**Step 8: Simulate**
- Same logic as evaluate; no DB writes; return computed results

**Step 9: Tests + fixtures**
- Unit tests; golden fixture; idempotency; RLS; simulate

**Step 10: Docker + Makefile + RUNBOOK**

---

## 11. Steampipe Platform Integration

The compliance engine **consumes** from the Steampipe execution platform. It does NOT run Steampipe.

| Platform Table | Purpose |
|----------------|---------|
| execution_jobs | tenant_id, account_id, query_id, status |
| execution_results | execution_job_id, snapshot_path, row_count |
| queries | id, name, query_text, extra_metadata (framework, control_ref, pass_rule, required_columns) |
| cloud_accounts | id, tenant_id, provider, account_id |

**Trigger:** When execution platform completes a compliance query, publish to Redis `compliance:job_completed` with `execution_job_id`, `snapshot_path`. Compliance worker: extract → evaluate.

**Hybrid tenant/account:** Denormalize `tenant_id`, `account_id` into compliance tables from `execution_jobs` at extract time. Fast filtering; RLS-friendly.

---

## 12. Out of Scope

- Running Steampipe or Powerpipe (execution platform does that)
- Risk scoring logic (separate Risk Engine)
- Full UI (API contract only)

---

**Use this document as the single implementation prompt.** For visual flow, see `docs/ARCHITECTURE_DIAGRAM.md`. For S3→Postgres details, see `docs/S3_TO_POSTGRES_MAPPING.md`.
