# Implementation Roadmap — Steampipe + Cloud Compliance

**Purpose:** Prioritized task list to complete **one by one**.  
**Last updated:** 2026-06-23

**Live checklist with completion status:** [TASK_TRACKER.md](TASK_TRACKER.md)

Mark tasks `[x]` when done. Do not skip dependency order unless noted.

---

## How to use this doc

1. Work top-to-bottom within each phase.
2. Each task has **ID**, **stage**, **effort**, **depends on**, and **done when**.
3. Stages: **S1** = Steampipe execution (`src/`, `:8000`), **S2** = Compliance (`cloud-compliance-engine/`, `:8001`), **Both** = integration.
4. Link related docs in the task notes — do not duplicate runbooks here.

**Quick refs**

| Topic | Doc |
|-------|-----|
| Platform overview | [COMPLIANCE_PLATFORM.md](COMPLIANCE_PLATFORM.md) |
| CIS scan (Stage 1) | [CIS_SCAN_RUNBOOK.md](CIS_SCAN_RUNBOOK.md) |
| Compliance runbook | [../cloud-compliance-engine/RUNBOOK.md](../cloud-compliance-engine/RUNBOOK.md) |
| Worker scaling | [SCALING_ROADMAP.md](SCALING_ROADMAP.md) |
| Remote DB / Redis | [RUN_WITH_REMOTE_DB.md](RUN_WITH_REMOTE_DB.md) |

---

## Status summary

| Phase | Focus | Tasks |
|-------|--------|-------|
| **0** | Finish MVP validation | T-001 – T-006 |
| **1** | Dev stability & data correctness | T-010 – T-015 |
| **2** | First customer / prod-ready | T-020 – T-028 |
| **3** | Product & scale | T-030 – T-038 |
| **4** | Enterprise & multi-framework | T-040 – T-048 |

---

## Phase 0 — Finish MVP validation (do first)

Goal: Prove full CIS scan → PASS/FAIL → API works on your machine.

| ID | Task | Stage | Effort | Depends | Done when |
|----|------|-------|--------|---------|-----------|
| **T-001** | Fix compliance `.env`: `COMPLIANCE_QUEUE_KEY=steampipe:job_completed`, `LOCAL_STORAGE_PATH`, load root `.env` | S2 | 15 min | — | Worker starts with Upstash Redis, no reconnect loop |
| **T-002** | Run DB at head: `alembic upgrade head` (006+) | Both | 5 min | — | `alembic_version` = 006 |
| **T-003** | Run setup: `python scripts/setup_compliance.py` | Both | 10 min | T-002 | `public.queries` + `compliance.controls` + `rule_versions.definitions` populated |
| **T-004** | Start stack: Steampipe Docker (`api` + `worker`) + compliance local (API `:8001` + worker) | Both | 20 min | T-001, T-003 | Both health checks OK |
| **T-005** | **E2E new scan:** `POST :8000/executions/scan` → worker completes → compliance worker processes 35 jobs | Both | 30 min | T-004 | `GET :8001/v1/scan-runs/{batch_id}` shows `completed`, score, 35 controls |
| **T-006** | Document test IDs & last good batch in your notes (tenant, account, batch_id) | Both | 5 min | T-005 | Repeatable test without guessing UUIDs |

**Phase 0 exit criteria:** One full CIS scan from trigger to compliance score without manual backfill.

---

## Phase 1 — Dev stability & data correctness

Goal: Trust results; no silent misconfig or stale data.

| ID | Task | Stage | Effort | Depends | Done when |
|----|------|-------|--------|---------|-----------|
| **T-010** | Reprocess legacy batches: `POST /v1/scan-runs/{batch}/process` for pre-006 snapshots | S2 | 30 min | T-005 | Snapshots have `rule_metadata`; results show `rule_source=bronze` |
| **T-011** | Verify bronze pinning: change one rule in `public.queries`, re-eval old batch — result unchanged | S2 | 1 hr | T-010 | Old batch still uses pinned hash; new scan uses new rule |
| **T-012** | Add `pass_rule` + `required_columns` to Redis `job_completed` payload (optional enrichment) | S1 | 1 hr | T-005 | Event includes metadata; compliance still works if Bronze missing |
| **T-013** | Compliance unit + integration tests in CI (pytest on push) | S2 | 2 hr | T-003 | GitHub Action or local script runs `cloud-compliance-engine/tests` |
| **T-014** | Stage 1 smoke test script (scan + poll batch status) | S1 | 2 hr | T-005 | Single script exits 0 on success |
| **T-015** | Update [COMPLIANCE_PLATFORM.md](COMPLIANCE_PLATFORM.md) with Phase 0–1 checklist link | Both | 15 min | T-005 | Doc links to this roadmap |

**Phase 1 exit criteria:** Reproducible tests; bronze immutability verified.

---

## Phase 2 — First customer / production-ready

Goal: Safe multi-tenant deploy; not just local dev.

| ID | Task | Stage | Effort | Depends | Done when |
|----|------|-------|--------|---------|-----------|
| **T-020** | **S3 snapshots:** `USE_LOCAL_STORAGE=false`, worker writes S3, compliance reads same paths | Both | 1–2 days | T-005 | Full scan with snapshots in S3; compliance score correct |
| **T-021** | IAM: worker write bucket; compliance read-only; no long-lived keys in `.env` where possible | Both | 1 day | T-020 | Task role / instance profile documented |
| **T-022** | **JWT auth** on Stage 1 API (`API_AUTH_REQUIRED=true`) | S1 | 1–2 days | T-005 | Scan requires valid token |
| **T-023** | **JWT auth** on compliance API (same tenant claim → `X-Tenant-Id` or from token) | S2 | 1–2 days | T-022 | All `/v1/*` require auth in prod |
| **T-024** | **RLS:** wire `get_db_with_tenant` on all compliance routes; worker sets tenant per event | S2 | 1 day | T-023 | Cross-tenant read impossible via API |
| **T-025** | Run compliance in Docker (not local-only): `compliance-api` + `compliance-worker` in `docker-compose.remote.yml` | S2 | 4 hr | T-001 | Same E2E as T-005 entirely in Docker |
| **T-026** | Secrets: remove AWS SSO tokens from committed files; document rotation | Both | 2 hr | — | `.env` gitignored; `env.example` only placeholders |
| **T-027** | **Drift detection:** set `status_changed` / `previous_status` on `control_results` when `control_state` flips | S2 | 1 day | T-010 | API or DB shows PASS→FAIL transitions |
| **T-028** | **Severity-weighted score** on `scan_runs` (optional column or derived in API) | S2 | 1–2 days | T-005 | Dashboard can show critical-weighted score |

**Phase 2 exit criteria:** Deployable to one prod environment with auth, S3, and tenant isolation.

---

## Phase 3 — Product & scale

Goal: Scheduled scans, faster runs, minimal UI or integrator experience.

| ID | Task | Stage | Effort | Depends | Done when |
|----|------|-------|--------|---------|-----------|
| **T-030** | **Scheduler → CIS scan:** cron triggers `framework_id=cis_aws_v6` per account | S1 | 2–3 days | T-025 | Nightly scan appears in `scan_runs` without manual curl |
| **T-031** | **Warm Steampipe service** per worker (Scaling Phase 2) | S1 | 1–2 wks | T-025 | Measurable drop in per-job init time |
| **T-032** | Horizontal scale runbook: `--scale worker=N` + compliance worker replica | Both | 1 day | T-025 | 3 workers drain queue 3× faster |
| **T-033** | **Unified “scan status” API** or BFF: one endpoint returns batch + compliance score | Both | 2–3 days | T-025 | UI needs one poll, not two ports |
| **T-034** | Minimal UI or internal dashboard (scan list, matrix, evidence) | S2 | 1–2 wks | T-033 | Non-engineer can view failures |
| **T-035** | Queue / scan **monitoring**: queue depth, failed jobs, compliance lag alerts | Both | 2–3 days | T-025 | Alert when worker down or scan stuck |
| **T-036** | **Multi-version rules:** seed `6.0.1` without overwriting `6.0.0`; eval pins version | S2 | 2–3 days | T-011 | Two versions coexist; audit shows version used |
| **T-037** | Manual CIS controls: mark non-automated in API (`status=manual`) | S2 | 1–2 days | T-005 | 63 catalog vs 35 automated clear in UI/API |
| **T-038** | **Split compliance repo** (optional): standalone repo, shared contracts doc | Both | 2–3 days | T-025 | Compliance deploys without Steampipe code |

**Phase 3 exit criteria:** Customers get scheduled scans, faster bulk runs, and a way to view results without curl.

---

## Phase 4 — Enterprise & multi-framework

Goal: Audit-grade, extensible platform.

| ID | Task | Stage | Effort | Depends | Done when |
|----|------|-------|--------|---------|-----------|
| **T-040** | **Hash chain** on `control_results` (`prev_result_hash` wired) | S2 | 2–3 days | T-027 | Tamper-evident evaluation chain per account |
| **T-041** | **Change events / webhooks** on drift (FAIL new or regressed) | S2 | 3–5 days | T-027 | HTTP webhook on status change |
| **T-042** | `POST /simulate` with `proposed_rules` (no DB write) | S2 | 1–2 days | T-036 | Policy what-if before publish |
| **T-043** | **Partition** `control_results` by month (Postgres) | S2 | 2–3 days | T-028 | Migration + query paths updated |
| **T-044** | **SOC2 / second framework** stub: catalog + 5 pilot controls | Both | 2–4 wks | T-036 | Second `framework_id` end-to-end |
| **T-045** | Azure or GCP CIS pilot (one provider) | Both | 4–8 wks | T-044 | Non-AWS account scan works |
| **T-046** | K8s/ECS job runner (Scaling Phase 4) | S1 | weeks | T-031 | Elastic workers beyond Compose |
| **T-047** | `control_metrics` + materialized view for dashboards | S2 | 1 wk | T-034 | Fast trend queries |
| **T-048** | SOC2 Type II evidence export (scan + rule hash + snapshot hash bundle) | S2 | 1–2 wks | T-040 | Export ZIP/JSON for auditor |

**Phase 4 exit criteria:** Enterprise sales / audit requirements met.

---

## Recommended order (next 5 tasks)

If you are picking up today, do these in sequence:

```
T-001 → T-002 → T-003 → T-004 → T-005
```

Then:

```
T-010 → T-011 → T-020 → T-022 → T-025
```

---

## Task log (fill as you go)

| ID | Completed | Notes |
|----|-----------|-------|
| T-001 | | |
| T-002 | | |
| T-003 | | |
| T-004 | | |
| T-005 | | |
| T-006 | | |

*(Add rows as you progress.)*

---

## Out of scope (v1)

- Full CIS certification claim (automated subset only)
- Powerpipe / AGPL mod execution in product
- Real-time continuous compliance (delta re-eval only)
- Customer-authored SQL in UI

---

## Related docs (do not duplicate)

- Worker performance: [SCALING_ROADMAP.md](SCALING_ROADMAP.md) — Phases 1–4 map to T-031, T-032, T-046
- Enterprise schema wish-list: [../cloud-compliance-engine/docs/archive/ENTERPRISE_ARCHITECTURE.md](../cloud-compliance-engine/docs/archive/ENTERPRISE_ARCHITECTURE.md)
- Old feature list: [CODE_STATUS_AND_FEATURES_TO_ADD.md](CODE_STATUS_AND_FEATURES_TO_ADD.md) — superseded by this roadmap for prioritization
