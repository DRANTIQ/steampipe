# Cloud Compliance Engine — Design

High-level design for the engine that turns **resource snapshots** into **control_results** and **compliance_summary**. For the **full architecture diagram** (Phase 1 → Phase 2, evaluation_runs, tables, rule engine, evidence, drift, API), see **[docs/ARCHITECTURE_DIAGRAM.md](docs/ARCHITECTURE_DIAGRAM.md)**. For **enterprise additions** (evaluation_runs, RLS, soft delete, hash chain, multi-cloud, partition strategy), see **[docs/ENTERPRISE_ARCHITECTURE.md](docs/ENTERPRISE_ARCHITECTURE.md)**.

---

## Architecture (recommended: extract first, then rules)

**Best mapping:** Extract snapshot data into DB first, then apply compliance rules from that DB. See **[docs/ARCHITECTURE_EXTRACT_VS_ENGINE.md](docs/ARCHITECTURE_EXTRACT_VS_ENGINE.md)** for the full comparison and schema.

```
┌─────────────────────────────────────────────────────────────────┐
│  Execution platform (Steampipe)                                  │
│  • execution_jobs, execution_results, snapshot_path (S3)         │
│  • queries.extra_metadata: framework, control_ref, pass_rule     │
└────────────────────────────┬────────────────────────────────────┘
                             │ snapshot_path + metadata
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  COMPLIANCE ENGINE (this repo)                                   │
│                                                                  │
│  Phase 1 — EXTRACT          Phase 2 — APPLY RULES                 │
│  ┌─────────────────────┐   ┌─────────────────────┐              │
│  │ S3 → execution_      │ → │ Read snapshot rows  │ → control_   │
│  │ snapshot_rows (DB)  │   │ Apply pass_rule      │   results    │
│  │ (one row per snapshot│   │ Build evidence      │   compliance_│
│  │  row; row_data JSONB)│   │                     │   summary    │
│  └─────────────────────┘   └─────────────────────┘              │
└─────────────────────────────────────────────────┼────────────────┘
                                                  │
                             ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Risk Engine (next)  →  API / Dashboard                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data flow

1. **Trigger:** Execution platform signals “job X finished; snapshot at path P; query has framework F, control_ref C, pass_rule R.”
2. **Extract (Phase 1):** Engine fetches snapshot JSON from S3; writes each row to `execution_snapshot_rows` (execution_job_id, row_index, row_data JSONB). Idempotent per execution.
3. **Filter:** Only run extract + evaluate for compliance queries (e.g. `category == "compliance"` and `framework` set).
4. **Evaluate (Phase 2):** Read rows from `execution_snapshot_rows` for this execution; apply pass_rule (e.g. zero_rows ⇒ pass if 0 rows, else fail); build evidence from required_columns.
5. **Write:** Insert/upsert into `control_results`; then refresh `compliance_summary` for that tenant/account/framework/period.
6. **Expose:** Risk Engine and API read control_results and compliance_summary.

---

## CIS v6 control mapping (example)

| control_ref (query)     | CIS v6 control_id | Description (from PDF)        |
|-------------------------|-------------------|-------------------------------|
| s3-versioning           | 2.1.1             | S3 bucket versioning          |
| s3-encryption           | 2.1.2             | S3 default encryption         |
| s3-public-access       | 2.1.3             | S3 block public access        |
| rds-public              | 4.1.x             | RDS not publicly accessible  |
| …                       | …                 | Map from CIS v6.0.0 PDF       |

Maintain this in `config/cis_v6_controls.yaml` (or CSV) and load at runtime. Use control_id in control_results for reporting and PDF alignment.

---

## Why this beats the rest

- **Wiz:** We don’t replicate their full CSPM; we focus on **CIS v6 + evidence** and a clear control_results table. Easier to audit and plug into your own risk model.
- **Drata:** We provide a **reusable engine** (not just a product): same pipeline for any tenant/account; framework and rules are config-driven.
- **Powerpipe:** We **don’t run** Powerpipe (AGPL). We consume **existing** Steampipe output and add a dedicated evaluation layer, so execution and compliance are cleanly separated and you avoid AGPL for this service.

---

## Reference

- **CIS benchmark:** `CIS_Amazon_Web_Services_Foundations_Benchmark_v6.0.0.pdf` (store in parent repo or docs; use for control IDs and titles).
- **Execution platform:** Queries and metadata live in the Steampipe platform repo; this engine only reads snapshots and metadata and writes control_results and compliance_summary.
