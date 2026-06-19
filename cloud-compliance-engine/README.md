# Cloud Compliance Engine

Production-grade, **enterprise-ready** compliance engine: two-phase (EXTRACT → RULES), **controls table** (first-class definitions + remediation), **control_state** cache, **evidence normalization** (JSONB + control_evidence_resources), **rule_definition_hash** + snapshot_hash (audit), severity-weighted scoring, drift detection, **change events stream**, **mv_latest_control_status**, **POST /simulate**, **framework_control_mappings**, partitioning.

```
Resources (S3) → Extract → execution_snapshot_rows → Rules → control_results + control_evidence_resources + control_state → compliance_summary → events → Risk Engine → API/Dashboard
```

- **Implementation prompt (start here):** **[IMPLEMENTATION_PROMPT.md](IMPLEMENTATION_PROMPT.md)** — Single source of truth: schema, API, extract/evaluate flow, step-by-step order, tests, runbook. Use this for building the engine.
- **Cursor prompt (feature spec):** **[PROMPT.md](PROMPT.md)** — evaluation_runs, controls, control_state, control_evidence_resources, RLS, canonical hashing, tamper protection, phased roadmap.
- **Enterprise checklist:** **[docs/ENTERPRISE_ARCHITECTURE.md](docs/ENTERPRISE_ARCHITECTURE.md)** — evaluation_runs, RLS, soft delete, hash chain, multi-cloud, partition strategy, SLA, control_metrics, observability.
- **Full architecture diagram:** **[docs/ARCHITECTURE_DIAGRAM.md](docs/ARCHITECTURE_DIAGRAM.md)** — Phase 1 → Phase 2, evaluation_runs lifecycle, all tables, rule engine, evidence, drift, API.
- **Design overview:** **[DESIGN.md](DESIGN.md)** — data flow, why we beat Wiz/Drata/Powerpipe.
- **Control mapping:** `config/cis_v6_controls.yaml` — CIS v6 control_id + severity; reference `CIS_Amazon_Web_Services_Foundations_Benchmark_v6.0.0.pdf`.
- **CIS v6 SQL queries:** `queries/cis_v6_queries.json` — Steampipe SQL for 34 automated controls; use with parent repo `data/queries.json` or apply via scripts.
- **Architecture:** `docs/ARCHITECTURE.md` — Modular monolith: same DB/Redis/S3, separate `compliance` schema and Redis namespace.
- **S3 → Postgres mapping:** `docs/S3_TO_POSTGRES_MAPPING.md` — Extract (S3 → compliance.execution_snapshot_rows), rule engine, compliance.control_results, compliance.compliance_summary.
- **Runbook:** **[RUNBOOK.md](RUNBOOK.md)** — Run locally, add controls/rules, simulate, evidence links, troubleshooting.
- **Adding frameworks/providers/categories:** **[docs/ADDING_FRAMEWORKS.md](docs/ADDING_FRAMEWORKS.md)** — Add future versions (e.g. CIS v7), providers (Azure, GCP), or categories (e.g. cost optimization) via config + catalog; no code change. Seed with `python -m app.scripts.seed_catalog`.

**Run (from repo root):**
```bash
alembic upgrade head
PYTHONPATH=cloud-compliance-engine python -m app.scripts.seed_catalog   # load controls + frameworks from config/catalog.yaml
PYTHONPATH=cloud-compliance-engine python -m uvicorn app.main:app --reload --app-dir cloud-compliance-engine --port 8000
```
Then open `http://localhost:8000/docs`. Use `X-Tenant-Id` header or set `DEFAULT_TENANT_ID` in `.env`.
