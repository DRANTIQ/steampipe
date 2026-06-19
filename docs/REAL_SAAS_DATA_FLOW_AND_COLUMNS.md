# Real SaaS: Data Flow, All Queries, and Required Columns for CIS/Controls

We are implementing **real SaaS**. This doc ties together: (1) the end-to-end flow, (2) how we accommodate **all queries** and **required columns**, and (3) how data extracted from JSON into the DB supports **CIS / control** pass–fail (Powerpipe CIS = **reference only**; we apply our own or aligned rules).

---

## 1. End-to-end flow

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────────────┐
│ Steampipe       │     │ Snapshot     │     │ Extract      │     │ CIS / control        │
│ (our queries)   │ ──► │ JSON → S3   │ ──► │ JSON → DB   │ ──► │ pass–fail & alarms   │
└─────────────────┘     └──────────────┘     └─────────────┘     └─────────────────────┘
       │                        │                    │                        │
       │ query_text             │ snapshot_path      │ rows in DB             │ control_results
       │ from Query table       │ on ExecutionResult │ (see §3)               │ (new tables)
```

1. **Steampipe** runs SQL from the **Query** table per account → result rows (JSON).
2. **Snapshot** JSON is written to **S3**; **ExecutionResult** stores `snapshot_path` (and job/query/account).
3. **Extract:** A separate process (or step) reads that JSON and loads it into **our DB** (or a dedicated analytics DB). That’s the “data is extracted to one of the db from json”.
4. **CIS / controls:** On that DB we **apply** control rules (CIS-style or SOC2, etc.). We **do not run Powerpipe** in our pipeline; we **reference** CIS/Powerpipe for rule meaning and implement **our own** pass–fail logic. Result: pass/fail per control, per account, stored in **control_results** (or similar) → then **alarms**.

So: **all information** we need is (a) every query we run, (b) the columns each query returns, (c) which columns each control needs to evaluate pass/fail, and (d) the schema of the “extracted” DB so the control engine can read it.

---

## 2. Accommodating all queries

| Need | How we accommodate it |
|------|------------------------|
| **Single list of queries** | **Query** table in DB + **QUERIES_CATALOG.md** as the doc of record. Add queries via API or seed; keep the catalog in sync. |
| **Scaling to many queries** | Use **query packs** (group of query IDs) when we need “run all CIS 4.0” etc. Optional `query_packs` table or `extra_metadata.pack_id`. |
| **Required columns per query** | Store in **Query.extra_metadata** as `required_columns` (or `output_columns`). Catalog doc lists them explicitly so extract + control logic know what to expect. |
| **Which query feeds which control** | **Query.extra_metadata**: `framework`, `control_id` / `control_ref`. Control definitions (later) reference `query_id` and the columns they need. |

So: **all queries** = everything in the Query table (and catalog). **Required columns** = per-query metadata + explicit list in the catalog for extract and CIS.

---

## 3. Extracting JSON to DB (so we can apply CIS/controls)

The snapshot JSON is an array of rows. When we **extract to DB**, we need a schema that:

- Links to **execution** (and thus account, tenant, query).
- Stores **one row per snapshot row** (or a JSONB blob), with **columns available for control logic**.

Two patterns:

| Pattern | Description | Use when |
|--------|--------------|----------|
| **A. One table per “result type”** | e.g. `snapshot_s3_buckets`, `snapshot_rds_instances`. Columns = key columns + every column the control needs. | You want to run SQL (e.g. “all buckets where versioning_enabled = false”) for CIS. |
| **B. One generic table** | e.g. `snapshot_rows(execution_result_id, query_id, row_index, data JSONB)`. All columns inside `data`. | You want flexibility; control engine reads JSONB. |

For **CIS/control pass–fail** we need at least:

- `execution_result_id` (or `execution_job_id`) → links to ExecutionResult and account/tenant.
- `query_id` → which query produced this data.
- **Required columns** for that query/control (either as real columns or inside JSONB).

So the **extract** step must:

- Know the **query_id** and its **required_columns** (from Query.extra_metadata or catalog).
- Write rows into the chosen schema (A or B) so that the **control evaluation** step can read the right fields (e.g. `versioning_enabled`, `publicly_accessible`).

---

## 4. Required columns per query (for catalog and metadata)

Below: **query name**, **columns returned** (what the SQL selects), and **columns required for CIS/control** evaluation. The extract step should preserve these; the control engine will use them.

| Query name | Columns returned | Required columns for CIS/control |
|------------|------------------|----------------------------------|
| list_ec2_instances | instance_id, instance_state, instance_type, placement_availability_zone | — (inventory only) |
| list_s3_buckets | name, region, account_id, creation_date | — (inventory only) |
| list_iam_users | name, user_id, path, create_date, password_last_used | — (inventory only) |
| list_rds_instances | db_instance_identifier, class, engine, engine_version, db_instance_status | — (inventory only) |
| ec2_count_by_az_and_type | az, instance_type, count | — (inventory only) |
| **s3_buckets_versioning_disabled** | name, region, account_id, versioning_enabled | **name, versioning_enabled** (fail if any row) |
| **s3_buckets_default_encryption_disabled** | name, server_side_encryption_configuration | **name, server_side_encryption_configuration** (fail if any row) |
| **s3_buckets_public_access_not_blocked** | name, block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets | **name**, **block_public_acls**, **block_public_policy**, **ignore_public_acls**, **restrict_public_buckets** (fail if any row) |
| s3_buckets_public_policy | name, bucket_policy_is_public | name, bucket_policy_is_public |
| ec2_detailed_monitoring_disabled | instance_id, monitoring_state | instance_id, monitoring_state |
| **rds_publicly_accessible** | db_instance_identifier, publicly_accessible | **db_instance_identifier, publicly_accessible** (fail if any row) |
| **rds_iam_auth_disabled** | db_instance_identifier, iam_database_authentication_enabled | **db_instance_identifier, iam_database_authentication_enabled** |
| iam_access_keys_inactive | access_key_id, user_name, status | access_key_id, user_name, status |
| iam_access_key_count_by_user | user_name, access_key_count | user_name, access_key_count |
| iam_users_with_admin_access | user_name, attached_policies | user_name, attached_policies |
| ec2_count_by_instance_type | instance_type, count | — (cost only) |
| list_ec2_instances_limit_5 | instance_id, instance_state | — (demo) |

**Storing required columns in the platform:** Put them in **Query.extra_metadata**, e.g.:

```json
{
  "framework": "CIS AWS Foundations 4.0",
  "control_ref": "s3-versioning",
  "required_columns": ["name", "versioning_enabled"],
  "pass_rule": "zero_rows"
}
```

Then the **extract** job and **control** engine can read `required_columns` (and optional `pass_rule`) from the Query row.

---

## 5. Summary: do we have all the information?

| Question | Answer |
|----------|--------|
| Real SaaS flow? | Yes: Steampipe → JSON (S3) → extract to DB → apply CIS/controls (our rules) → pass/fail & alarms. |
| Powerpipe CIS? | **Reference only.** We don’t run Powerpipe; we apply our own (or aligned) control logic on the extracted DB. |
| Accommodate all queries? | Yes: Query table + QUERIES_CATALOG.md; optionally query packs for “all CIS” runs. |
| Required columns? | Yes: (1) this doc lists them per query, (2) store in Query.extra_metadata.required_columns (and optional pass_rule). |
| Data extracted to DB from JSON? | Yes: extract step reads snapshot JSON, writes to our DB (per-query or generic table) with columns needed for control evaluation. |
| Apply CIS/controls there? | Yes: control engine runs on that DB, uses required_columns and pass_rule, writes control_results → alarms. |

We have what we need to implement: keep the catalog and `extra_metadata` (including `required_columns`) in sync, define the extract schema (e.g. one table per result type or one generic snapshot_rows table), and implement the control evaluation step that reads from the extracted DB and writes pass/fail.
