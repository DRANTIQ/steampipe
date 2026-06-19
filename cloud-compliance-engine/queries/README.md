# CIS v6 SQL Queries

Steampipe SQL queries for **CIS AWS Foundations Benchmark v6.0.0** automated controls.

## File

- **`cis_v6_queries.json`** — 34 queries covering automated controls from sections 2 (IAM), 3 (Storage), 4 (Logging), 5 (Monitoring), 6 (Networking).

## Usage

### With parent Steampipe platform

Merge into `../data/queries.json` or use `scripts/apply_queries_document.py` with a combined document. Each query needs:

- `name`, `query_text`, `provider`, `plugin`, `execution_mode`, `output_format`
- `extra_metadata`: `category: "compliance"`, `framework`, `control_ref`, `required_columns`, `pass_rule`

### Pass rule

- **`pass_rule: "zero_rows"`** — 0 rows returned = PASS. Rows returned = FAIL (non-compliant resources).

### Control mapping

`control_ref` maps to `config/cis_v6_controls.yaml` for `control_id`, `severity`, `title`.

## Dependencies

- **Steampipe** with **AWS plugin**: `steampipe plugin install aws`
- Tables used: `aws_iam_account_summary`, `aws_iam_account_password_policy`, `aws_iam_user`, `aws_iam_access_key`, `aws_iam_role`, `aws_s3_bucket`, `aws_rds_db_instance`, `aws_efs_file_system`, `aws_cloudtrail_trail`, `aws_config_configuration_recorder`, `aws_kms_key`, `aws_kms_key_rotation`, `aws_vpc`, `aws_vpc_flow_log`, `aws_vpc_security_group`, `aws_vpc_security_group_rule`, `aws_vpc_network_acl`, `aws_vpc_network_acl_entry`, `aws_ec2_instance`, `aws_ec2_regional_settings`, `aws_accessanalyzer_analyzer`, `aws_securityhub_hub`, `aws_region`, `aws_account`, `aws_iam_user_group_membership`, `aws_iam_server_certificate`

## Notes

- Some queries may need adjustment for your Steampipe AWS plugin version.
- Manual controls (2.1, 2.2, 2.5, 2.6, 2.10, 3.1.2, 3.1.3, 3.2.4, 4.1, 4.4, 5.1–5.15, 6.6) have no SQL automation.
