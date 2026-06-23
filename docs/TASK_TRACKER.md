# Task Tracker — Steampipe + Cloud Compliance Engine

**Purpose:** Master checklist for all implementation work. Mark `[x]` as you complete items.  
**Last updated:** 2026-06-23  
**Detail / rationale:** [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)  
**Repo split:** [SPLIT_COMPLIANCE_REPO.md](SPLIT_COMPLIANCE_REPO.md)

**Stages:** **S1** = Steampipe (`src/`, `:8000`) · **S2** = Compliance (`cloud-compliance-engine/`, `:8001`) · **Both** = integration

---

## Current status (2026-06-23)

| Area | Status |
|------|--------|
| Phase 0 MVP | ~90% — backfill works; confirm automatic E2E (T-005) |
| Compliance in Docker | Done — separate repo `cloud-compliance-engine` |
| Snapshot mount fix | Done — `SNAPSHOT_VOLUME` → Steampipe `local/snapshots` |
| Repo split (T-038) | ~80% — Phase C monorepo cleanup pending |
| Phase 1+ | Not started |

### Test IDs (repeatable runs)

| Item | Value |
|------|-------|
| Tenant (slug) | `drantiq_sandbox` / `5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47` |
| Account UUID | `e0e0075b-310d-4e37-9997-81626fe52580` |
| AWS account | `387957186076` |
| Framework | `cis_aws_v6` (35 automated controls) |
| Last good batch | `7425e74e-a5b2-4d22-b958-a5559d8c02e4` |
| Last scan run | `821204de-2d41-45a2-bd6a-7956bbda5204` (27 pass / 8 fail / 77.14%) |
| Prior backfill batch | `beef0081-5617-4ca4-bf6a-5480dd7aeab4` |

### Docker compliance (required env)

```env
SNAPSHOT_VOLUME=C:/Users/devar/OneDrive/Documents/GitHub/steampipe/local/snapshots
LOCAL_STORAGE_PATH=/data/snapshots   # inside container (set by docker-compose)
COMPLIANCE_QUEUE_KEY=steampipe:job_completed
```

---

## Recommended next 5

```
[ ] T-005  — Fresh scan, automatic (no POST /process)
[ ] T-006  — Confirm test IDs above in your runbook
[ ] T-010  — Reprocess legacy batches for rule_metadata
[ ] T-011  — Verify bronze pinning
[ ] SPLIT-C — Clean steampipe monorepo (remove duplicate compliance)
```

---

## Phase 0 — Finish MVP validation

**Goal:** Full CIS scan → PASS/FAIL → compliance API without manual backfill.  
**Exit criteria:** `GET :8001/v1/scan-runs/{batch_id}` → `completed`, 35 controls, score.

| ID | Status | Task | Stage | Effort | Depends | Done when |
|----|--------|------|-------|--------|---------|-----------|
| T-001 | [x] | Fix compliance `.env`: `COMPLIANCE_QUEUE_KEY=steampipe:job_completed`, `LOCAL_STORAGE_PATH`, Redis socket timeout | S2 | 15 min | — | Worker starts with Upstash Redis, no reconnect loop |
| T-002 | [x] | DB at head: `python -m alembic stamp 004` / `upgrade head` in compliance repo | Both | 5 min | — | `alembic_version_compliance` at head |
| T-003 | [x] | Setup: `python -m app.scripts.seed_catalog` (compliance repo) | Both | 10 min | T-002 | `compliance.controls` + `rule_versions.definitions` populated |
| T-004 | [x] | Start stack: Steampipe Docker (`api` + `worker`) + compliance Docker (`:8001` + worker) | Both | 20 min | T-001, T-003 | Both services healthy |
| T-005 | [~] | **E2E new scan:** `POST :8000/executions/scan` → compliance worker processes 35 jobs automatically | Both | 30 min | T-004 | Scan completes without `POST /process` |
| T-006 | [~] | Document test IDs & last good batch | Both | 5 min | T-005 | Repeatable test without guessing UUIDs |

**Notes**

- T-005 partial: batch `7425e74e-...` succeeded via manual `/process` after `SNAPSHOT_VOLUME` fix; still need one fully automatic run.
- Only **one** compliance worker on `steampipe:job_completed` (no local + Docker duplicate).

---

## Phase 1 — Dev stability & data correctness

**Goal:** Trust results; no silent misconfig or stale data.  
**Exit criteria:** Reproducible tests; bronze immutability verified.

| ID | Status | Task | Stage | Effort | Depends | Done when |
|----|--------|------|-------|--------|---------|-----------|
| T-010 | [ ] | Reprocess legacy batches: `POST /v1/scan-runs/{batch}/process` for pre-006 snapshots | S2 | 30 min | T-005 | Snapshots have `rule_metadata`; `rule_source=bronze` |
| T-011 | [ ] | Verify bronze pinning: change rule in `public.queries`, re-eval old batch unchanged | S2 | 1 hr | T-010 | Old batch pinned; new scan uses new rule |
| T-012 | [x] | Add `pass_rule` + `required_columns` to Redis `job_completed` payload | S1 | 1 hr | T-005 | `job_completed_event.py` + publishers |
| T-013 | [x] | Compliance unit + integration tests in CI (pytest on push) | S2 | 2 hr | T-003 | `.github/workflows/ci.yml` |
| T-014 | [x] | Stage 1 smoke test script (scan + poll batch status) | S1 | 2 hr | T-005 | `scripts/smoke_e2e_scan.py` |
| T-015 | [x] | Update COMPLIANCE_PLATFORM.md + [PHASE1.md](PHASE1.md) | Both | 15 min | T-005 | Doc links to tracker + Phase 1 guide |

### Phase 1 extras (from ops)

| ID | Status | Task | Stage | Done when |
|----|--------|------|-------|-----------|
| T-015a | [ ] | Document `SNAPSHOT_VOLUME` in compliance README + RUNBOOK as required for Docker | S2 | New devs don't hit empty `./data/snapshots` mount |
| T-015b | [ ] | Log extract failure reason (file not found vs parse error) in compliance worker | S2 | Worker logs show why extract failed |
| T-015c | [ ] | Optional: requeue / dead-letter on extract failure instead of dropping Redis event | S2 | Failed jobs recoverable without `/process` |

---

## Phase 2 — First customer / production-ready

**Goal:** Safe multi-tenant deploy.  
**Exit criteria:** Deployable prod with auth, S3, tenant isolation.

| ID | Status | Task | Stage | Effort | Depends | Done when |
|----|--------|------|-------|--------|---------|-----------|
| T-020 | [ ] | **S3 snapshots:** `USE_LOCAL_STORAGE=false`, worker writes S3, compliance reads same paths | Both | 1–2 days | T-005 | Full scan; compliance score correct from S3 |
| T-021 | [ ] | IAM: worker write bucket; compliance read-only; no long-lived keys in `.env` | Both | 1 day | T-020 | Task role / instance profile documented |
| T-022 | [ ] | **JWT auth** on Stage 1 API (`API_AUTH_REQUIRED=true`) | S1 | 1–2 days | T-005 | Scan requires valid token |
| T-023 | [ ] | **JWT auth** on compliance API (tenant from token or `X-Tenant-Id`) | S2 | 1–2 days | T-022 | All `/v1/*` require auth in prod |
| T-024 | [ ] | **RLS:** `get_db_with_tenant` on compliance routes; worker sets tenant per event | S2 | 1 day | T-023 | Cross-tenant read impossible via API |
| T-025 | [x] | Compliance in Docker: `compliance-api` + `compliance-worker` in compliance repo `docker-compose.yml` | S2 | 4 hr | T-001 | E2E in Docker (with `SNAPSHOT_VOLUME`) |
| T-026 | [ ] | Secrets: remove AWS SSO tokens from committed files; document rotation | Both | 2 hr | — | `.env` gitignored; examples use placeholders only |
| T-027 | [ ] | **Drift detection:** `status_changed` / `previous_status` on `control_results` | S2 | 1 day | T-010 | API/DB shows PASS→FAIL transitions |
| T-028 | [ ] | **Severity-weighted score** on `scan_runs` | S2 | 1–2 days | T-005 | Dashboard can show critical-weighted score |

---

## Phase 3 — Product & scale

**Goal:** Scheduled scans, faster runs, minimal UI.  
**Exit criteria:** Nightly scans, faster bulk runs, view results without curl.

| ID | Status | Task | Stage | Effort | Depends | Done when |
|----|--------|------|-------|--------|---------|-----------|
| T-030 | [ ] | **Scheduler → CIS scan:** cron triggers `framework_id=cis_aws_v6` per account | S1 | 2–3 days | T-025 | Nightly scan in `scan_runs` without manual curl |
| T-031 | [ ] | **Warm Steampipe service** per worker (Scaling Phase 2) | S1 | 1–2 wks | T-025 | Drop in per-job init time |
| T-032 | [ ] | Horizontal scale: `--scale worker=N` + compliance worker replica | Both | 1 day | T-025 | 3 workers drain queue ~3× faster |
| T-033 | [ ] | **Unified scan status API** / BFF: batch + compliance score in one poll | Both | 2–3 days | T-025 | UI needs one endpoint, not two ports |
| T-034 | [ ] | Minimal UI or internal dashboard (scan list, matrix, evidence) | S2 | 1–2 wks | T-033 | Non-engineer can view failures |
| T-035 | [ ] | Queue / scan **monitoring**: depth, failed jobs, compliance lag alerts | Both | 2–3 days | T-025 | Alert when worker down or scan stuck |
| T-036 | [ ] | **Multi-version rules:** seed `6.0.1` without overwriting `6.0.0` | S2 | 2–3 days | T-011 | Two versions coexist; audit shows version |
| T-037 | [ ] | Manual CIS controls: `status=manual` for non-automated in API | S2 | 1–2 days | T-005 | 63 catalog vs 35 automated clear in API |
| T-038 | [~] | **Split compliance repo:** standalone repo + `contracts/STAGE1_INTEGRATION.md` | Both | 2–3 days | T-025 | Compliance deploys without Steampipe code |

---

## Phase 4 — Enterprise & multi-framework

**Goal:** Audit-grade, extensible platform.  
**Exit criteria:** Enterprise / audit requirements met.

| ID | Status | Task | Stage | Effort | Depends | Done when |
|----|--------|------|-------|--------|---------|-----------|
| T-040 | [ ] | **Hash chain** on `control_results` (`prev_result_hash` wired) | S2 | 2–3 days | T-027 | Tamper-evident chain per account |
| T-041 | [ ] | **Change events / webhooks** on drift (new FAIL or regression) | S2 | 3–5 days | T-027 | HTTP webhook on status change |
| T-042 | [ ] | `POST /simulate` with `proposed_rules` (no DB write) | S2 | 1–2 days | T-036 | Policy what-if before publish |
| T-043 | [ ] | **Partition** `control_results` by month (Postgres) | S2 | 2–3 days | T-028 | Migration + queries updated |
| T-044 | [ ] | **SOC2 / second framework** stub: catalog + 5 pilot controls | Both | 2–4 wks | T-036 | Second `framework_id` end-to-end |
| T-045 | [ ] | Azure or GCP CIS pilot (one provider) | Both | 4–8 wks | T-044 | Non-AWS account scan works |
| T-046 | [ ] | K8s/ECS job runner (Scaling Phase 4) | S1 | weeks | T-031 | Elastic workers beyond Compose |
| T-047 | [ ] | `control_metrics` + materialized view for dashboards | S2 | 1 wk | T-034 | Fast trend queries |
| T-048 | [ ] | SOC2 Type II evidence export (scan + rule hash + snapshot hash bundle) | S2 | 1–2 wks | T-040 | Export ZIP/JSON for auditor |

---

## Repo split checklist (T-038)

### Phase A — Prepare

| ID | Status | Task |
|----|--------|------|
| SPLIT-A1 | [x] | Compliance config standalone (no `import src.config`) |
| SPLIT-A2 | [x] | Snapshot path resolution (`local/snapshots/` strip + join) |
| SPLIT-A3 | [x] | Alembic `001`–`004` in compliance repo (`alembic_version_compliance`) |
| SPLIT-A4 | [x] | `cloud-compliance-engine/docker-compose.yml` |
| SPLIT-A5 | [x] | `contracts/STAGE1_INTEGRATION.md` |
| SPLIT-A6 | [x] | Compliance `.env.example` with `SNAPSHOT_VOLUME` |

### Phase B — Create new repo

| ID | Status | Task |
|----|--------|------|
| SPLIT-B1 | [x] | GitHub repo `cloud-compliance-engine` created |
| SPLIT-B2 | [x] | App copied / populated in sibling repo |

### Phase C — Clean steampipe monorepo

| ID | Status | Task |
|----|--------|------|
| SPLIT-C1 | [ ] | Remove `cloud-compliance-engine/` from steampipe repo (or git submodule) |
| SPLIT-C2 | [ ] | Remove compliance services from `docker-compose.remote.yml` |
| SPLIT-C3 | [ ] | Trim steampipe alembic to `001`–`002` only (compliance migrations in other repo) |
| SPLIT-C4 | [ ] | Update `docs/COMPLIANCE_PLATFORM.md` with link to external repo |
| SPLIT-C5 | [ ] | Remove or thin `scripts/setup_compliance.py`; document two-repo setup |

### Phase D — Deploy both

| ID | Status | Task |
|----|--------|------|
| SPLIT-D1 | [x] | Steampipe: `docker compose -f docker-compose.remote.yml up` (`:8000`) |
| SPLIT-D2 | [x] | Compliance: `docker compose up` in compliance repo (`:8001`) |
| SPLIT-D3 | [x] | Shared `DATABASE_URL`, `REDIS_URL`, snapshot volume |

---

## Integration contracts (do not break)

| Contract | Owner | Consumer |
|----------|--------|----------|
| Postgres `public.execution_*` | S1 | S2 (read) |
| Postgres `compliance.*` | S2 | S2 (write) |
| Redis `steampipe:job_completed` | S1 publish | S2 worker consume |
| Bronze JSON schema v1.0 | S1 write | S2 read |
| `public.queries.extra_metadata` | S1 seed | S2 rules (primary) |

Full spec: `cloud-compliance-engine/contracts/STAGE1_INTEGRATION.md`

---

## Out of scope (v1)

- Full CIS certification claim (automated subset only)
- Powerpipe / AGPL mod execution in product
- Real-time continuous compliance (delta re-eval only)
- Customer-authored SQL in UI

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) | Phased plan + effort estimates |
| [SPLIT_COMPLIANCE_REPO.md](SPLIT_COMPLIANCE_REPO.md) | Repo split cutover |
| [COMPLIANCE_PLATFORM.md](COMPLIANCE_PLATFORM.md) | Architecture overview |
| [SCALING_ROADMAP.md](SCALING_ROADMAP.md) | T-031, T-032, T-046 |
| `cloud-compliance-engine/RUNBOOK.md` | Ops setup & troubleshoot |
| `cloud-compliance-engine/docs/API.md` | REST reference |

---

## Completion log

| ID | Completed | Notes |
|----|-----------|-------|
| T-001 | 2026-06-22 | Queue key, Redis timeout, Upstash |
| T-002 | 2026-06-22 | `alembic stamp 004` in compliance repo |
| T-003 | 2026-06-22 | `seed_catalog` |
| T-004 | 2026-06-23 | Steampipe remote + compliance Docker |
| T-005 | — | Backfill OK; automatic E2E pending |
| T-006 | — | IDs captured in this doc |
| T-025 | 2026-06-23 | Compliance Docker + `SNAPSHOT_VOLUME` |
| T-038 | ~2026-06-23 | Repo split; Phase C pending |

*(Add a row when you finish each task.)*
