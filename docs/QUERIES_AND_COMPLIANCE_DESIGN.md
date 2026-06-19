# Queries, Licensing, and Future Compliance Design

This document finalizes how we **save and reference queries**, stay **license-safe** (Powerpipe vs Steampipe), and keep the **base compatible** with future analysis (S3 → DB → CIS/SOC2 pass–fail and alarms). **No implementation yet** — design only.

---

## 1. Licensing: What We Use vs What We Only Reference

### 1.1 Powerpipe and AGPL

- **Powerpipe** (the engine that runs benchmarks and dashboards) is **AGPL-3.0**.
- If we **run Powerpipe** inside our service (API/worker) or **embed/distribute** Powerpipe or mod code as part of our product, we could have AGPL obligations (e.g. source disclosure, same license for network use).
- **Intended approach:** We **do not use** Powerpipe mods or benchmarks as “our” queries. We **only reference** them:
  - Run Powerpipe **outside** our pipeline (e.g. manually, or in a separate process the user controls).
  - We do **not** store Powerpipe mod HCL/control definitions in our DB.
  - We do **not** call Powerpipe from our execution worker or API.
- The `powerpipe/` folder in the repo is for **local/reference use** (e.g. run benchmarks manually, read control definitions). It is **not** part of the automated execution path.

**Conclusion:** Powerpipe mods = **reference only**. We do not embed or execute them in our service.

### 1.2 Steampipe and Plugins

- **Steampipe** (query engine) and the **AWS plugin** (turbot/aws) are **Apache-2.0** (permissive).
- We **can use** Steampipe and plugin tables in our product:
  - Run `steampipe query` with **our own SQL** (or SQL from non-AGPL sources).
  - Store that SQL in our **Query** table and execute it via our worker.
  - Use plugin table docs (e.g. in `plugins/.../docs/tables/`) as reference for writing queries.

**Conclusion:** Steampipe queries (SQL against plugin tables) = **OK to use and store** in our platform.

### 1.3 Where CIS / SOC2 compliance “frameworks” actually live

- **Steampipe** does **not** ship CIS or SOC2 frameworks or compliance queries. It gives you **plugin tables** (e.g. `aws_s3_bucket`, `aws_iam_user`) — the *data*. You write SQL against those tables.
- The **full CIS benchmarks and SOC2-style compliance packs** (hundreds of controls, pre-built) are in **Powerpipe mods** (e.g. `steampipe-mod-aws-compliance`). You run those via **Powerpipe**, not Steampipe. So: **all CIS frameworks and SOC2 compliance benchmarks = Powerpipe (mods), not inside Steampipe.**
- **Our approach:** We use **Steampipe only**. We write **our own SQL** that implements CIS-style or SOC2-style checks using the same plugin tables. We tag them with `framework` / `control_ref` in metadata. We do **not** run Powerpipe or use its mod content, so we have a **subset** of checks (the ones in our queries document), not the full Powerpipe benchmark set.
- **For test:** We apply **only the queries in our document** (`data/queries.json`) — a curated subset for testing and SaaS. The CIS “framework” alignment in our metadata is **from us** (we say “this query aligns to CIS-style s3-versioning”), not from Powerpipe or from Steampipe.
- **Metadata (framework, control_ref, pass_rule) and pass/fail:** All of these are **for reference** — our own labels and rules. We do not pull CIS or pass/fail definitions from Powerpipe; we tag queries and define how we evaluate (e.g. pass when zero rows).

---

## 2. How We Save Queries and Data for Analysis

### 2.1 What Lives in the Query Table

- **Only Steampipe-compatible SQL** that we are allowed to run and store:
  - Our own SQL.
  - SQL from permissive sources (e.g. Apache-2.0, MIT, or our own compliance checks we author).
- **We do not store:**
  - Powerpipe mod HCL or control definitions (AGPL mod content).
  - Any “import” that would copy AGPL benchmark code into our DB.

**Current `Query` model (no change required for license safety):**

- `query_text`: our SQL (e.g. `select * from aws_ec2_instance where ...`).
- `provider`, `plugin`: e.g. `aws`, `turbot/aws`.
- `name`, `version`: for identity and versioning.
- `extra_metadata`: optional JSON for **reference** info (see below).

### 2.2 Optional: Reference to Frameworks/Controls (No AGPL Content)

If we want to **align** our queries to a framework (CIS, SOC2, etc.) without using Powerpipe mod code:

- Use **`extra_metadata`** (or a future optional column) to store **references only**, for example:
  - `framework`: `"CIS AWS Foundations 4.0"`, `"SOC2"`, etc.
  - `control_id` or `control_ref`: e.g. `"1.2.3"` (our label, not their code).
- The **query_text** remains **our SQL** (written by us or from permissive sources). We are not storing or executing Powerpipe/AGPL mod content.

This keeps the base **compatible** with later “control X / framework Y” reporting and alarms without touching AGPL.

### 2.3 “Importing” Queries

- **Import** = bringing a query (SQL) into our platform and saving it in the **Query** table.
- Allowed:
  - Paste/upload **SQL** that runs against Steampipe plugin tables.
  - SQL we author or that comes from permissive-licensed sources.
- Not allowed as “our” stored queries:
  - Importing Powerpipe mod HCL or benchmark definitions as the source of truth we execute.
- We may **document** that a given row in `Query` “maps to” or “implements a check similar to” a CIS/SOC2 control (via `extra_metadata`), without storing the mod’s code.

---

## 3. Saving Data for Analysis (Current and Future)

### 3.1 Current Flow

- Worker runs **Steampipe** with `query_text` from **Query**.
- Raw result (JSON) is written to **S3**; path is stored in **ExecutionResult.snapshot_path**.
- **ExecutionResult** also stores: status, row_count, duration_seconds, plugin/Steampipe versions, etc. No “pass/fail” or control-level data yet.

### 3.2 Future Flow (For Your Knowledge — Not Implemented Yet)

Planned high-level flow:

1. **Snapshot on S3**  
   Already in place: JSON per execution.

2. **Analysis step**  
   A separate process (or step) reads that JSON, evaluates it (e.g. against rules or control definitions we own), and produces:
   - Pass/fail per control or per check.
   - Optional summary per framework (CIS, SOC2).

3. **Persist to DB**  
   Save analysis output (e.g. control results, pass/fail, severity) in the DB — **new tables** (e.g. `control_results`, `analysis_runs`, or similar), not in the current `Query` or `ExecutionResult` tables.  
   `ExecutionResult` stays as “run + snapshot pointer”; analysis results live in analysis-specific tables.

4. **Alarms**  
   Use the stored analysis to drive CIS/SOC2 (or other) pass–fail and alarms (e.g. per control, per account, per tenant).

### 3.3 Base Design for Compatibility

- **Query:** Stays the single place for “what we run” — Steampipe SQL only; optional framework/control **references** in metadata.
- **ExecutionResult:** Keeps pointing to S3 (snapshot_path); no need to store full JSON in DB for the base.
- **New analysis tables (later):**  
  - Keyed by execution (or snapshot) and optionally by query / control / framework.  
  - Store pass/fail, severity, and any fields needed for alarms.  
- **Security:**  
  - No AGPL code in our execution path or DB.  
  - Access to S3 and DB stays tenant/account-scoped as today.

This keeps the base **secure and compatible** with the future analysis and alarm flow without requiring changes to how we store “queries” today.

---

## 4. Summary

| Topic | Decision |
|-------|----------|
| **Powerpipe mods** | **Reference only.** We do not run or store Powerpipe/AGPL mod content in our service or DB. |
| **Steampipe queries** | **We use them.** We store and execute our own SQL (or permissive-licensed SQL) against plugin tables. |
| **Query table** | Stores **only** Steampipe-compatible SQL; optional `extra_metadata` for framework/control **references** (no AGPL content). |
| **Import** | Allowed for SQL we can run (our own or permissive). Not for Powerpipe mod definitions as our executed queries. |
| **Analysis / pass–fail / alarms** | Future: S3 JSON → analysis → **new DB tables** → CIS/SOC2 (or other) pass–fail and alarms. Base design stays compatible. |

Once this is agreed, we can implement the “importing” and any small Query metadata extensions without touching Powerpipe execution or AGPL content.

For **architect / senior DB engineer ideas** on the best way to save queries (versioning, tenancy, storage, metadata, packs, indexing), see [QUERY_STORAGE_IDEAS.md](QUERY_STORAGE_IDEAS.md).
