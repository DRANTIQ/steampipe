# Queries Catalog — All SQL Queries Saved in the Query Table

This document lists **all SQL queries** the platform stores in the `queries` table. The **queries document** applied into the table is **`data/queries.json`**; use **`scripts/apply_queries_document.py`** to load it. See [QUERIES_DOCUMENT_SPEC.md](QUERIES_DOCUMENT_SPEC.md). Each query is Steampipe-compatible (AWS plugin). Use this as the single reference for what we run; add or change rows here when you add/update queries via API or seed.

**Conventions:**

- **Provider:** `aws` (others, e.g. `azure`, when plugins are added).
- **Plugin:** `aws` (turbot/aws).
- **Execution mode:** `single_account` unless noted.
- **Output format:** `json`.
- **extra_metadata** may include: `framework`, `control_id`, `category`, `source`, and for control/CIS: **`required_columns`** (list of column names the extract + control engine must preserve), **`pass_rule`** (e.g. `zero_rows` = pass when query returns no rows). See [REAL_SAAS_DATA_FLOW_AND_COLUMNS.md](REAL_SAAS_DATA_FLOW_AND_COLUMNS.md).

All SQL below is **Postgres-style** (as used by Steampipe).

**Provenance:** The queries in this catalog were **curated and written for this doc** (not auto-extracted from the plugin). They are **adapted from the example SQL** in the **plugin table docs** in this repo:

- **Location:** `plugins/hub.steampipe.io/plugins/turbot/aws@latest/docs/tables/*.md`
- Each table doc (e.g. `aws_ec2_instance.md`, `aws_s3_bucket.md`) has an **Examples** section with ready-to-use SQL. Those examples come from the Steampipe Hub (Turbot).
- We took a subset of those examples (and simple variants), gave them names/versions, and grouped them here. So: **logic and columns = from plugin table examples; catalog structure and choice of queries = written for this project.**
- To add more queries: open the relevant table doc under `plugins/.../docs/tables/`, copy or adapt the example SQL, add a row to this catalog, then save to the `queries` table via API or seed.

---

## 1. Inventory & discovery

| Name | Version | Provider | Plugin | Category | extra_metadata (optional) | SQL (query_text) |
|------|---------|----------|--------|----------|---------------------------|------------------|
| list_ec2_instances | 1.0 | aws | aws | inventory | — | `select instance_id, instance_state, instance_type, placement_availability_zone from aws_ec2_instance;` |
| list_s3_buckets | 1.0 | aws | aws | inventory | — | `select name, region, account_id, creation_date from aws_s3_bucket;` |
| list_iam_users | 1.0 | aws | aws | inventory | — | `select name, user_id, path, create_date, password_last_used from aws_iam_user;` |
| list_rds_instances | 1.0 | aws | aws | inventory | — | `select db_instance_identifier, class, engine, engine_version, db_instance_status from aws_rds_db_instance;` |
| ec2_count_by_az_and_type | 1.0 | aws | aws | inventory | — | `select placement_availability_zone as az, instance_type, count(*) from aws_ec2_instance group by placement_availability_zone, instance_type;` |

---

## 2. Security & compliance (governance)

| Name | Version | Provider | Plugin | Category | extra_metadata (optional) | SQL (query_text) |
|------|---------|----------|--------|----------|---------------------------|------------------|
| s3_buckets_versioning_disabled | 1.0 | aws | aws | compliance | framework: CIS-style, control_ref: s3-versioning | `select name, region, account_id, versioning_enabled from aws_s3_bucket where not versioning_enabled;` |
| s3_buckets_default_encryption_disabled | 1.0 | aws | aws | compliance | framework: CIS-style, control_ref: s3-encryption | `select name, server_side_encryption_configuration from aws_s3_bucket where server_side_encryption_configuration is null;` |
| s3_buckets_public_access_not_blocked | 1.0 | aws | aws | compliance | framework: CIS-style, control_ref: s3-public-access | `select name, block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets from aws_s3_bucket where not block_public_acls or not block_public_policy or not ignore_public_acls or not restrict_public_buckets;` |
| s3_buckets_public_policy | 1.0 | aws | aws | compliance | — | `select name, bucket_policy_is_public from aws_s3_bucket where bucket_policy_is_public;` |
| ec2_detailed_monitoring_disabled | 1.0 | aws | aws | compliance | — | `select instance_id, monitoring_state from aws_ec2_instance where monitoring_state = 'disabled';` |
| rds_publicly_accessible | 1.0 | aws | aws | compliance | framework: CIS-style, control_ref: rds-public | `select db_instance_identifier, publicly_accessible from aws_rds_db_instance where publicly_accessible;` |
| rds_iam_auth_disabled | 1.0 | aws | aws | compliance | — | `select db_instance_identifier, iam_database_authentication_enabled from aws_rds_db_instance where not iam_database_authentication_enabled;` |
| iam_access_keys_inactive | 1.0 | aws | aws | compliance | — | `select access_key_id, user_name, status from aws_iam_access_key where status = 'Inactive';` |
| iam_access_key_count_by_user | 1.0 | aws | aws | compliance | — | `select user_name, count(access_key_id) as access_key_count from aws_iam_access_key group by user_name;` |
| iam_users_with_admin_access | 1.0 | aws | aws | compliance | — | `select name as user_name, split_part(attachments, '/', 2) as attached_policies from aws_iam_user cross join jsonb_array_elements_text(attached_policy_arns) as attachments where split_part(attachments, '/', 2) = 'AdministratorAccess';` |

---

## 3. Cost & optimization (optional)

| Name | Version | Provider | Plugin | Category | extra_metadata (optional) | SQL (query_text) |
|------|---------|----------|--------|----------|---------------------------|------------------|
| ec2_count_by_instance_type | 1.0 | aws | aws | cost | — | `select instance_type, count(instance_type) as count from aws_ec2_instance group by instance_type;` |

---

## 4. Placeholder / minimal (existing seed-style)

| Name | Version | Provider | Plugin | Category | extra_metadata (optional) | SQL (query_text) |
|------|---------|----------|--------|----------|---------------------------|------------------|
| list_ec2_instances_limit_5 | 1.0 | aws | aws | inventory | — | `select instance_id, instance_state from aws_ec2_instance limit 5;` |

---

## 5. Single reference table (copy-paste into DB/API)

Below, each query as one row: **name**, **version**, **provider**, **plugin**, **query_text**. Omit id (UUID generated); set **execution_mode** = `single_account`, **output_format** = `json`, **active** = true, **schedule_enabled** = false unless you override.

| name | version | provider | plugin | query_text |
|------|---------|----------|--------|------------|
| list_ec2_instances | 1.0 | aws | aws | `select instance_id, instance_state, instance_type, placement_availability_zone from aws_ec2_instance;` |
| list_s3_buckets | 1.0 | aws | aws | `select name, region, account_id, creation_date from aws_s3_bucket;` |
| list_iam_users | 1.0 | aws | aws | `select name, user_id, path, create_date, password_last_used from aws_iam_user;` |
| list_rds_instances | 1.0 | aws | aws | `select db_instance_identifier, class, engine, engine_version, db_instance_status from aws_rds_db_instance;` |
| ec2_count_by_az_and_type | 1.0 | aws | aws | `select placement_availability_zone as az, instance_type, count(*) from aws_ec2_instance group by placement_availability_zone, instance_type;` |
| s3_buckets_versioning_disabled | 1.0 | aws | aws | `select name, region, account_id, versioning_enabled from aws_s3_bucket where not versioning_enabled;` |
| s3_buckets_default_encryption_disabled | 1.0 | aws | aws | `select name, server_side_encryption_configuration from aws_s3_bucket where server_side_encryption_configuration is null;` |
| s3_buckets_public_access_not_blocked | 1.0 | aws | aws | `select name, block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets from aws_s3_bucket where not block_public_acls or not block_public_policy or not ignore_public_acls or not restrict_public_buckets;` |
| s3_buckets_public_policy | 1.0 | aws | aws | `select name, bucket_policy_is_public from aws_s3_bucket where bucket_policy_is_public;` |
| ec2_detailed_monitoring_disabled | 1.0 | aws | aws | `select instance_id, monitoring_state from aws_ec2_instance where monitoring_state = 'disabled';` |
| rds_publicly_accessible | 1.0 | aws | aws | `select db_instance_identifier, publicly_accessible from aws_rds_db_instance where publicly_accessible;` |
| rds_iam_auth_disabled | 1.0 | aws | aws | `select db_instance_identifier, iam_database_authentication_enabled from aws_rds_db_instance where not iam_database_authentication_enabled;` |
| iam_access_keys_inactive | 1.0 | aws | aws | `select access_key_id, user_name, status from aws_iam_access_key where status = 'Inactive';` |
| iam_access_key_count_by_user | 1.0 | aws | aws | `select user_name, count(access_key_id) as access_key_count from aws_iam_access_key group by user_name;` |
| iam_users_with_admin_access | 1.0 | aws | aws | `select name as user_name, split_part(attachments, '/', 2) as attached_policies from aws_iam_user cross join jsonb_array_elements_text(attached_policy_arns) as attachments where split_part(attachments, '/', 2) = 'AdministratorAccess';` |
| ec2_count_by_instance_type | 1.0 | aws | aws | `select instance_type, count(instance_type) as count from aws_ec2_instance group by instance_type;` |
| list_ec2_instances_limit_5 | 1.0 | aws | aws | `select instance_id, instance_state from aws_ec2_instance limit 5;` |

---

## 6. Raw SQL only (for scripts / import)

Use these as `query_text` when inserting into the `queries` table (e.g. seed script or import job).

```sql
select instance_id, instance_state, instance_type, placement_availability_zone from aws_ec2_instance;
select name, region, account_id, creation_date from aws_s3_bucket;
select name, user_id, path, create_date, password_last_used from aws_iam_user;
select db_instance_identifier, class, engine, engine_version, db_instance_status from aws_rds_db_instance;
select placement_availability_zone as az, instance_type, count(*) from aws_ec2_instance group by placement_availability_zone, instance_type;
select name, region, account_id, versioning_enabled from aws_s3_bucket where not versioning_enabled;
select name, server_side_encryption_configuration from aws_s3_bucket where server_side_encryption_configuration is null;
select name, block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets from aws_s3_bucket where not block_public_acls or not block_public_policy or not ignore_public_acls or not restrict_public_buckets;
select name, bucket_policy_is_public from aws_s3_bucket where bucket_policy_is_public;
select instance_id, monitoring_state from aws_ec2_instance where monitoring_state = 'disabled';
select db_instance_identifier, publicly_accessible from aws_rds_db_instance where publicly_accessible;
select db_instance_identifier, iam_database_authentication_enabled from aws_rds_db_instance where not iam_database_authentication_enabled;
select access_key_id, user_name, status from aws_iam_access_key where status = 'Inactive';
select user_name, count(access_key_id) as access_key_count from aws_iam_access_key group by user_name;
select name as user_name, split_part(attachments, '/', 2) as attached_policies from aws_iam_user cross join jsonb_array_elements_text(attached_policy_arns) as attachments where split_part(attachments, '/', 2) = 'AdministratorAccess';
select instance_type, count(instance_type) as count from aws_ec2_instance group by instance_type;
select instance_id, instance_state from aws_ec2_instance limit 5;
```

---

## 7. How to use this catalog

- **Add a query:** Add a row to the tables above (and to section 5 and 6 if you want them in sync), then create the query via API `POST /api/v1/queries` or seed script.
- **Change a query:** Update the row here and the corresponding `query_text` in the DB (new version or in-place per your versioning policy).
- **Framework/control alignment:** Set `extra_metadata.framework` and `extra_metadata.control_id` / `control_ref` for compliance reporting (no AGPL content; see [QUERIES_AND_COMPLIANCE_DESIGN.md](QUERIES_AND_COMPLIANCE_DESIGN.md)).
- **Table reference:** Column names and more examples come from `plugins/hub.steampipe.io/plugins/turbot/aws@latest/docs/tables/*.md` and [PLUGIN_TABLES_REFERENCE.md](PLUGIN_TABLES_REFERENCE.md).

This catalog is the single doc of **all queries we save in the query table**.

---

## 8. Required columns for control/CIS (extract → DB → pass/fail)

For each **compliance** query, the data extracted from JSON to DB must include these columns so CIS/control logic can evaluate pass/fail. Store them in **Query.extra_metadata.required_columns** (and optional **pass_rule**, e.g. `zero_rows`).

| Query name | required_columns | pass_rule (typical) |
|------------|------------------|----------------------|
| s3_buckets_versioning_disabled | name, versioning_enabled | zero_rows |
| s3_buckets_default_encryption_disabled | name, server_side_encryption_configuration | zero_rows |
| s3_buckets_public_access_not_blocked | name, block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets | zero_rows |
| s3_buckets_public_policy | name, bucket_policy_is_public | zero_rows |
| ec2_detailed_monitoring_disabled | instance_id, monitoring_state | zero_rows |
| rds_publicly_accessible | db_instance_identifier, publicly_accessible | zero_rows |
| rds_iam_auth_disabled | db_instance_identifier, iam_database_authentication_enabled | zero_rows |
| iam_access_keys_inactive | access_key_id, user_name, status | — |
| iam_access_key_count_by_user | user_name, access_key_count | — |
| iam_users_with_admin_access | user_name, attached_policies | zero_rows (or threshold) |

Full flow (Steampipe → S3 JSON → extract to DB → CIS/controls): [REAL_SAAS_DATA_FLOW_AND_COLUMNS.md](REAL_SAAS_DATA_FLOW_AND_COLUMNS.md).
