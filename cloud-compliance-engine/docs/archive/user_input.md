# Cloud Compliance Engine — User Input

Fill in the sections below. Use this file when asking Cursor (or any implementer) to build or customize the compliance engine.

---

## 1. Decisions

### 1.1 Rule execution

- [ ] **Option A:** DSL compiled to parameterized SQL (recommended; no raw SQL from config)
- [ ] **Option B:** Validated SQL templates (whitelist tables, bindvars only)

**Your choice:** _e.g. Option A_

---

### 1.2 Auth / tenant context

- [ ] **Local dev only:** `X-Tenant-Id` header → `SET LOCAL app.tenant_id`
- [ ] **JWT later:** Same for now; add JWT claim `tenant_id` in a later phase
- [ ] **Other:** _describe_

**Your choice:** _e.g. X-Tenant-Id for now_

---

### 1.3 Partitioning

- [ ] **MVP:** Plain tables first; add partitioning in Phase 2
- [ ] **Now:** Partition large append-only tables by `tenant_id` + month

**Your choice:** _e.g. MVP (plain tables)_

---

### 1.4 Evidence sources for v1

- [ ] **Steampipe only** (S3 snapshot JSON from execution platform)
- [ ] **Steampipe + CloudTrail** (add CloudTrail parser in v1)
- [ ] **Steampipe + AWS Config**
- [ ] **Steampipe + SecurityHub**
- [ ] **All of the above**

**Your choice:** _e.g. Steampipe only_

---

## 2. Configuration (local dev)

**Copy `cloud-compliance-engine/.env.example` to `.env` and fill in values.**

### 2.1 Postgres

```
POSTGRES_HOST=
POSTGRES_PORT=5432
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
# Full URL (optional):
# DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

---

### 2.2 S3 / object storage

- [ ] **Local filesystem only** (no S3/MinIO for now)
- [ ] **MinIO** (S3-compatible local)
- [ ] **Real AWS S3**

**If MinIO:**
```
S3_ENDPOINT_URL=http://localhost:9000
S3_BUCKET=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
# Leave blank for MinIO default
```

**If AWS S3:**
```
S3_BUCKET=
AWS_REGION=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
# AWS_SESSION_TOKEN=  # if using temporary credentials
```

---

### 2.3 Redis (for job-completion queue)

- [ ] **Not used in v1** (trigger extract/evaluate via API or inline)
- [ ] **Local Redis**

**If Redis:**
```
REDIS_URL=redis://localhost:6379/0
# Compliance queue key (e.g. compliance:job_completed):
COMPLIANCE_QUEUE_KEY=
```

---

### 2.4 Application

```
# Tenant used when X-Tenant-Id not provided (dev only):
DEFAULT_TENANT_ID=

# Log level: DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=INFO
```

---

## 3. Sample evidence / fixtures

### 3.1 Steampipe snapshot (S3 or local path)

Path or pattern to 1–2 sample snapshot files used for tests and golden fixtures:

- **PASS example** (control should pass, e.g. 0 violation rows):  
  _e.g. `fixtures/sample_snapshot_pass.json` or `s3://bucket/.../result.json`_

- **FAIL example** (control should fail, with violations):  
  _e.g. `fixtures/sample_snapshot_fail.json`_

**Or:** _e.g. "Use the structure from docs/S3_TO_POSTGRES_MAPPING.md; I'll add files later."_

---

### 3.2 Expected control_results (optional)

If you have a golden list of expected control results for a given snapshot:

_e.g. `fixtures/expected_control_results.json` or "Generate from first run."_

---

## 4. Org-specific / constraints

### 4.1 Data retention

- **Raw snapshot rows:** keep for _e.g. 90_ days (or "no automatic purge").
- **control_results / compliance_summary:** _e.g. retain indefinitely, or _N_ months._

---

### 4.2 Audit / compliance

- Any extra fields to store per run or per result? _e.g. ticket_id, change_window, approver_
- Any required tags or labels on controls? _e.g. scope_type, scope_value_

---

### 4.3 Security

- All tables must be tenant-scoped (RLS): **yes / no**
- Any tables that must **not** live in the `compliance` schema? _e.g. none_

---

## 5. Implementation scope (check what you want)

- [ ] Alembic migrations only (schema)
- [ ] Migrations + hash utilities + config loaders
- [ ] Full pipeline: extract + evaluate + control_state + compliance_summary
- [ ] API (all endpoints in IMPLEMENTATION_PROMPT §7)
- [ ] POST /v1/simulate (dry-run evaluation)
- [ ] Docker Compose + Makefile
- [ ] RUNBOOK.md
- [ ] Tests (unit + integration + fixtures)
- [ ] All of the above (full implementation)

**Your choice:** _e.g. All of the above_

---

## 6. References (no need to edit)

- Implementation spec: `IMPLEMENTATION_PROMPT.md`
- S3 → Postgres: `docs/S3_TO_POSTGRES_MAPPING.md`
- Control definitions: `config/cis_v6_controls.yaml`
- Query catalog: `queries/cis_v6_queries.json`

---

_After filling this in, you can say: "Implement the compliance engine using the choices in user_input.md."_
