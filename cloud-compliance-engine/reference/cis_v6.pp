# CIS AWS Foundations Benchmark v6.0.0 — 34 Automated Control Queries
# Pass rule: zero_rows (0 rows = PASS, rows returned = FAIL)
# Run: steampipe query cis_2_3_iam_root_access_keys

query "cis_2_3_iam_root_access_keys" {
  title       = "CIS 2.3: Ensure no root user account access key exists"
  description = "Returns rows if root has access keys (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select account_id, account_access_keys_present from aws_iam_account_summary where account_access_keys_present > 0
  EOT
}

query "cis_2_4_iam_root_mfa" {
  title       = "CIS 2.4: Ensure MFA is enabled for the root user account"
  description = "Returns rows if root has password but no MFA (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select account_id, account_mfa_enabled, account_password_present from aws_iam_account_summary where not account_mfa_enabled and account_password_present
  EOT
}

query "cis_2_7_iam_password_min_length" {
  title       = "CIS 2.7: Ensure IAM password policy requires minimum length of 14 or greater"
  description = "Returns rows if policy allows < 14 chars (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select minimum_password_length from aws_iam_account_password_policy where minimum_password_length < 14 or minimum_password_length is null
  EOT
}

query "cis_2_8_iam_password_reuse" {
  title       = "CIS 2.8: Ensure IAM password policy prevents password reuse"
  description = "Returns rows if reuse prevention not set (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select password_reuse_prevention from aws_iam_account_password_policy where password_reuse_prevention is null or password_reuse_prevention = 0
  EOT
}

query "cis_2_9_iam_user_mfa" {
  title       = "CIS 2.9: Ensure MFA is enabled for all IAM users with console password"
  description = "Returns users with password but no MFA (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select u.name, u.user_id, u.create_date, u.mfa_enabled from aws_iam_user u where u.password_last_used is not null and (not u.mfa_enabled or u.mfa_enabled is null)
  EOT
}

query "cis_2_11_iam_credentials_unused" {
  title       = "CIS 2.11: Ensure credentials unused for 45 days or more are disabled"
  description = "Returns active credentials unused 45+ days (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select access_key_id, user_name, status, create_date, access_key_last_used_date from aws_iam_access_key where status = 'Active' and (access_key_last_used_date is null or access_key_last_used_date < (now() - interval '45 days'))
  EOT
}

query "cis_2_12_iam_single_access_key" {
  title       = "CIS 2.12: Ensure there is only one active access key per IAM user"
  description = "Returns users with >1 active key (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select user_name, count(*) as access_key_count from aws_iam_access_key where status = 'Active' group by user_name having count(*) > 1
  EOT
}

query "cis_2_13_iam_access_key_rotation" {
  title       = "CIS 2.13: Ensure access keys are rotated every 90 days or less"
  description = "Returns keys older than 90 days (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select access_key_id, user_name, create_date from aws_iam_access_key where status = 'Active' and create_date < (now() - interval '90 days')
  EOT
}

query "cis_2_14_iam_permissions_via_groups" {
  title       = "CIS 2.14: Ensure IAM users receive permissions only through groups"
  description = "Returns users with direct policies but no groups (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select u.name as user_name, u.user_id from aws_iam_user u where u.attached_policy_arns is not null and jsonb_array_length(u.attached_policy_arns) > 0 and (u.groups is null or jsonb_array_length(u.groups) = 0)
  EOT
}

query "cis_2_15_iam_admin_policies" {
  title       = "CIS 2.15: Ensure IAM policies with full *:* admin are not attached"
  description = "Returns users/roles with AdministratorAccess (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name as user_name, split_part(attachments, '/', 2) as attached_policy from aws_iam_user cross join jsonb_array_elements_text(attached_policy_arns) as attachments where split_part(attachments, '/', 2) = 'AdministratorAccess' union all select r.name as role_name, split_part(attachments, '/', 2) as attached_policy from aws_iam_role r cross join jsonb_array_elements_text(attached_policy_arns) as attachments where split_part(attachments, '/', 2) = 'AdministratorAccess'
  EOT
}

query "cis_2_16_iam_support_role" {
  title       = "CIS 2.16: Ensure a support role has been created for AWS Support"
  description = "Returns account if no AWSSupportAccess role (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select a.account_id from aws_account a where not exists (select 1 from aws_iam_role r where r.attached_policy_arns::text like '%AWSSupportAccess%')
  EOT
}

query "cis_2_17_iam_instance_roles" {
  title       = "CIS 2.17: Ensure IAM instance roles are used for AWS resource access"
  description = "Returns instances without IAM role (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select instance_id, instance_state, iam_instance_profile_arn from aws_ec2_instance where iam_instance_profile_arn is null and instance_state != 'terminated'
  EOT
}

query "cis_2_18_iam_expired_certificates" {
  title       = "CIS 2.18: Ensure expired SSL/TLS certificates in IAM are removed"
  description = "Returns expired certificates (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, server_certificate_id, upload_date, expiration from aws_iam_server_certificate where expiration < now()
  EOT
}

query "cis_2_19_iam_access_analyzer" {
  title       = "CIS 2.19: Ensure IAM Access Analyzer is enabled for all regions"
  description = "Returns regions where Access Analyzer not ACTIVE (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select region, name, status from aws_accessanalyzer_analyzer where status != 'ACTIVE'
  EOT
}

query "cis_3_1_1_s3_deny_http" {
  title       = "CIS 3.1.1: Ensure S3 Bucket Policy denies HTTP requests"
  description = "Returns buckets without SecureTransport policy (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, region, account_id from aws_s3_bucket where name not in (select name from aws_s3_bucket, jsonb_array_elements(policy_std -> 'Statement') as s, jsonb_array_elements_text(s -> 'Principal' -> 'AWS') as p, jsonb_array_elements_text(s -> 'Action') as a, jsonb_array_elements_text(s -> 'Condition' -> 'Bool' -> 'aws:securetransport') as ssl where p = '*' and s ->> 'Effect' = 'Deny' and ssl::bool = false)
  EOT
}

query "cis_3_1_4_s3_public_access" {
  title       = "CIS 3.1.4: Ensure S3 Block Public Access is enabled"
  description = "Returns buckets with public access not fully blocked (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, block_public_acls, block_public_policy, ignore_public_acls, restrict_public_buckets from aws_s3_bucket where not block_public_acls or not block_public_policy or not ignore_public_acls or not restrict_public_buckets
  EOT
}

query "cis_3_2_1_rds_encryption" {
  title       = "CIS 3.2.1: Ensure RDS encryption-at-rest is enabled"
  description = "Returns unencrypted RDS instances (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select db_instance_identifier, storage_encrypted from aws_rds_db_instance where storage_encrypted = false
  EOT
}

query "cis_3_2_2_rds_auto_upgrade" {
  title       = "CIS 3.2.2: Ensure RDS Auto Minor Version Upgrade is enabled"
  description = "Returns RDS with auto upgrade disabled (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select db_instance_identifier, auto_minor_version_upgrade from aws_rds_db_instance where auto_minor_version_upgrade = false
  EOT
}

query "cis_3_2_3_rds_public" {
  title       = "CIS 3.2.3: Ensure RDS instances are not publicly accessible"
  description = "Returns publicly accessible RDS (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select db_instance_identifier, publicly_accessible from aws_rds_db_instance where publicly_accessible = true
  EOT
}

query "cis_3_3_1_efs_encryption" {
  title       = "CIS 3.3.1: Ensure EFS encryption is enabled"
  description = "Returns unencrypted EFS file systems (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select file_system_id, name, encrypted from aws_efs_file_system where encrypted = false
  EOT
}

query "cis_4_2_cloudtrail_validation" {
  title       = "CIS 4.2: Ensure CloudTrail log file validation is enabled"
  description = "Returns trails without validation (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, region, log_file_validation_enabled from aws_cloudtrail_trail where log_file_validation_enabled = false
  EOT
}

query "cis_4_3_config_enabled" {
  title       = "CIS 4.3: Ensure AWS Config is enabled in all regions"
  description = "Returns regions with Config not recording (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, region, status_recording from aws_config_configuration_recorder where not status_recording
  EOT
}

query "cis_4_5_cloudtrail_kms" {
  title       = "CIS 4.5: Ensure CloudTrail logs are encrypted with KMS"
  description = "Returns trails without KMS encryption (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, region, kms_key_id from aws_cloudtrail_trail where kms_key_id is null
  EOT
}

query "cis_4_6_kms_rotation" {
  title       = "CIS 4.6: Ensure KMS key rotation is enabled for customer CMKs"
  description = "Returns customer keys without rotation (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select k.id, k.region, k.key_rotation_enabled from aws_kms_key k where k.key_manager = 'CUSTOMER' and (not k.key_rotation_enabled or k.key_rotation_enabled is null)
  EOT
}

query "cis_4_7_vpc_flow_logs" {
  title       = "CIS 4.7: Ensure VPC flow logging is enabled in all VPCs"
  description = "Returns VPCs without active flow logs (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select v.vpc_id, v.region from aws_vpc v where not exists (select 1 from aws_vpc_flow_log f where f.resource_id = v.vpc_id and f.deliver_logs_status = 'SUCCESS')
  EOT
}

query "cis_4_8_s3_write_logging" {
  title       = "CIS 4.8: Ensure object-level write logging for S3 is enabled"
  description = "Returns buckets without CloudTrail write logging (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, region from aws_s3_bucket where not exists (select 1 from aws_cloudtrail_trail t, jsonb_array_elements(t.event_selectors) as es where (es->'DataResources')::text like '%s3%' and es->>'ReadWriteType' = 'Write')
  EOT
}

query "cis_4_9_s3_read_logging" {
  title       = "CIS 4.9: Ensure object-level read logging for S3 is enabled"
  description = "Returns buckets without CloudTrail read logging (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select name, region from aws_s3_bucket where not exists (select 1 from aws_cloudtrail_trail t, jsonb_array_elements(t.event_selectors) as es where (es->'DataResources')::text like '%s3%' and (es->>'ReadWriteType' = 'ReadOnly' or es->>'ReadWriteType' = 'All'))
  EOT
}

query "cis_5_16_security_hub_enabled" {
  title       = "CIS 5.16: Ensure AWS Security Hub is enabled"
  description = "Returns regions without Security Hub (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select region from aws_region r where not exists (select 1 from aws_securityhub_hub h where h.region = r.region)
  EOT
}

query "cis_6_1_1_ebs_encryption_default" {
  title       = "CIS 6.1.1: Ensure EBS encryption is enabled by default"
  description = "Returns regions without default EBS encryption (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select region, default_ebs_encryption_enabled from aws_ec2_regional_settings where default_ebs_encryption_enabled = false
  EOT
}

query "cis_6_1_2_cifs_restricted" {
  title       = "CIS 6.1.2: Ensure CIFS access is restricted to trusted networks"
  description = "Returns SGs allowing CIFS (445) from 0.0.0.0/0 (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select sg.group_id, sg.group_name, sg.vpc_id, r.from_port, r.to_port, r.cidr_ipv4, r.cidr_ipv6 from aws_vpc_security_group sg join aws_vpc_security_group_rule r on sg.group_id = r.group_id where not r.is_egress and r.from_port <= 445 and r.to_port >= 445 and (r.cidr_ipv4 = '0.0.0.0/0' or r.cidr_ipv6 = '::/0')
  EOT
}

query "cis_6_2_nacl_admin_ports" {
  title       = "CIS 6.2: Ensure NACLs do not allow ingress to admin ports from 0.0.0.0/0"
  description = "Returns NACLs allowing SSH/RDP from 0.0.0.0/0 (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select acl.network_acl_id, acl.region, acl.account_id from aws_vpc_network_acl acl, jsonb_array_elements(acl.entries) as att where att->>'Egress' = 'false' and (att->>'CidrBlock' = '0.0.0.0/0' or att->>'Ipv6CidrBlock' = '::/0') and att->>'RuleAction' = 'allow' and ((att->>'Protocol' = '-1' and att->'PortRange' is null) or (att->'PortRange' is not null and att->>'Protocol' in ('6','17') and (((att->'PortRange'->>'From')::int <= 22 and (att->'PortRange'->>'To')::int >= 22) or ((att->'PortRange'->>'From')::int <= 3389 and (att->'PortRange'->>'To')::int >= 3389))))
  EOT
}

query "cis_6_3_sg_admin_ports_ipv4" {
  title       = "CIS 6.3: Ensure no SGs allow SSH/RDP from 0.0.0.0/0 (IPv4)"
  description = "Returns SGs allowing admin ports from 0.0.0.0/0 (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select sg.group_id, sg.group_name, r.from_port, r.to_port, r.cidr_ipv4 from aws_vpc_security_group sg join aws_vpc_security_group_rule r on sg.group_id = r.group_id where not r.is_egress and r.cidr_ipv4 = '0.0.0.0/0' and ((r.from_port <= 22 and r.to_port >= 22) or (r.from_port <= 3389 and r.to_port >= 3389))
  EOT
}

query "cis_6_4_sg_admin_ports_ipv6" {
  title       = "CIS 6.4: Ensure no SGs allow SSH/RDP from ::/0 (IPv6)"
  description = "Returns SGs allowing admin ports from ::/0 (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select sg.group_id, sg.group_name, r.from_port, r.to_port, r.cidr_ipv6 from aws_vpc_security_group sg join aws_vpc_security_group_rule r on sg.group_id = r.group_id where not r.is_egress and r.cidr_ipv6 = '::/0' and ((r.from_port <= 22 and r.to_port >= 22) or (r.from_port <= 3389 and r.to_port >= 3389))
  EOT
}

query "cis_6_5_default_sg_restricts_traffic" {
  title       = "CIS 6.5: Ensure default SG restricts all traffic"
  description = "Returns default SGs with permissive ingress (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select sg.group_id, sg.group_name, sg.vpc_id from aws_vpc_security_group sg where sg.group_name = 'default' and exists (select 1 from aws_vpc_security_group_rule r where r.group_id = sg.group_id and not r.is_egress and (r.cidr_ipv4 = '0.0.0.0/0' or r.cidr_ipv6 = '::/0'))
  EOT
}

query "cis_6_7_ec2_imdsv2" {
  title       = "CIS 6.7: Ensure EC2 Metadata Service only allows IMDSv2"
  description = "Returns instances without IMDSv2 required (FAIL). Zero rows = PASS."
  sql         = <<-EOT
    select instance_id, instance_state, metadata_options from aws_ec2_instance where (metadata_options->>'HttpTokens') is distinct from 'required' and instance_state != 'terminated'
  EOT
}
