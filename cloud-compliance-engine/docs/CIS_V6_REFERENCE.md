# CIS AWS Foundations Benchmark v6.0.0 — Full Control Reference

Extracted from `CIS_Amazon_Web_Services_Foundations_Benchmark_v6.0.0.pdf` (277 pages, Sep 2025).

---

## Profile Definitions

| Profile | Description |
|---------|-------------|
| **Level 1** | Practical, prudent; security-focused best practice; limited impact to utility. |
| **Level 2** | Extends Level 1; for environments where security > manageability; defense in depth; may impact utility/performance. |

**Note:** Most controls are Level 1. Control **5.16** (AWS Security Hub) is **Level 2**.

---

## Complete Control List

### 2 — Identity and Access Management

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 2.1 | Maintain current contact details | Manual | Level 1 | Account/Billing |
| 2.2 | Ensure security contact information is registered | Manual | Level 1 | Account |
| 2.3 | Ensure no 'root' user account access key exists | Automated | Level 1 | IAM |
| 2.4 | Ensure MFA is enabled for the 'root' user account | Automated | Level 1 | IAM |
| 2.5 | Ensure hardware MFA is enabled for the 'root' user account | Manual | Level 1 | IAM |
| 2.6 | Eliminate use of the 'root' user for administrative and daily tasks | Manual | Level 1 | IAM |
| 2.7 | Ensure IAM password policy requires minimum length of 14 or greater | Automated | Level 1 | IAM |
| 2.8 | Ensure IAM password policy prevents password reuse | Automated | Level 1 | IAM |
| 2.9 | Ensure multi-factor authentication (MFA) is enabled for all IAM users that have a console password | Automated | Level 1 | IAM |
| 2.10 | Do not create access keys during initial setup for IAM users with a console password | Manual | Level 1 | IAM |
| 2.11 | Ensure credentials unused for 45 days or more are disabled | Automated | Level 1 | IAM |
| 2.12 | Ensure there is only one active access key for any single IAM user | Automated | Level 1 | IAM |
| 2.13 | Ensure access keys are rotated every 90 days or less | Automated | Level 1 | IAM |
| 2.14 | Ensure IAM users receive permissions only through groups | Automated | Level 1 | IAM |
| 2.15 | Ensure IAM policies that allow full "*:*" administrative privileges are not attached | Automated | Level 1 | IAM |
| 2.16 | Ensure a support role has been created to manage incidents with AWS Support | Automated | Level 1 | IAM |
| 2.17 | Ensure IAM instance roles are used for AWS resource access from instances | Automated | Level 1 | IAM |
| 2.18 | Ensure that all expired SSL/TLS certificates stored in AWS IAM are removed | Automated | Level 1 | IAM |
| 2.19 | Ensure that IAM External Access Analyzer is enabled for all regions | Automated | Level 1 | IAM/Access Analyzer |
| 2.20 | Ensure IAM users are managed centrally via identity federation or AWS Organizations for multi-account environments | Manual | Level 1 | IAM |
| 2.21 | Ensure access to AWSCloudShellFullAccess is restricted | Manual | Level 1 | IAM |

---

### 3 — Storage

#### 3.1 Simple Storage Service (S3)

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 3.1.1 | Ensure S3 Bucket Policy is set to deny HTTP requests | Automated | Level 1 | S3 |
| 3.1.2 | Ensure MFA Delete is enabled on S3 buckets | Manual | Level 1 | S3 |
| 3.1.3 | Ensure all data in Amazon S3 has been discovered, classified, and secured when necessary | Manual | Level 1 | S3 |
| 3.1.4 | Ensure that S3 is configured with 'Block Public Access' enabled | Automated | Level 1 | S3 |

#### 3.2 Relational Database Service (RDS)

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 3.2.1 | Ensure that encryption-at-rest is enabled for RDS instances | Automated | Level 1 | RDS |
| 3.2.2 | Ensure the Auto Minor Version Upgrade feature is enabled for RDS instances | Automated | Level 1 | RDS |
| 3.2.3 | Ensure that RDS instances are not publicly accessible | Automated | Level 1 | RDS |
| 3.2.4 | Ensure Multi-AZ deployments are used for enhanced availability in Amazon RDS | Manual | Level 1 | RDS |

#### 3.3 Elastic File System (EFS)

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 3.3.1 | Ensure that encryption is enabled for EFS file systems | Automated | Level 1 | EFS |

---

### 4 — Logging

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 4.1 | Ensure CloudTrail is enabled in all regions | Manual | Level 1 | CloudTrail |
| 4.2 | Ensure CloudTrail log file validation is enabled | Automated | Level 1 | CloudTrail |
| 4.3 | Ensure AWS Config is enabled in all regions | Automated | Level 1 | Config |
| 4.4 | Ensure that server access logging is enabled on the CloudTrail S3 bucket | Manual | Level 1 | CloudTrail/S3 |
| 4.5 | Ensure CloudTrail logs are encrypted at rest using KMS CMKs | Automated | Level 1 | CloudTrail/KMS |
| 4.6 | Ensure rotation for customer-created symmetric CMKs is enabled | Automated | Level 1 | KMS |
| 4.7 | Ensure VPC flow logging is enabled in all VPCs | Automated | Level 1 | VPC |
| 4.8 | Ensure that object-level logging for write events is enabled for S3 buckets | Automated | Level 1 | CloudTrail/S3 |
| 4.9 | Ensure that object-level logging for read events is enabled for S3 buckets | Automated | Level 1 | CloudTrail/S3 |

---

### 5 — Monitoring

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 5.1 | Ensure unauthorized API calls are monitored | Manual | Level 1 | CloudWatch |
| 5.2 | Ensure management console sign-in without MFA is monitored | Manual | Level 1 | CloudWatch |
| 5.3 | Ensure usage of the 'root' account is monitored | Manual | Level 1 | CloudWatch |
| 5.4 | Ensure IAM policy changes are monitored | Manual | Level 1 | CloudWatch |
| 5.5 | Ensure CloudTrail configuration changes are monitored | Manual | Level 1 | CloudWatch |
| 5.6 | Ensure AWS Management Console authentication failures are monitored | Manual | Level 1 | CloudWatch |
| 5.7 | Ensure disabling or scheduled deletion of customer created CMKs is monitored | Manual | Level 1 | CloudWatch |
| 5.8 | Ensure S3 bucket policy changes are monitored | Manual | Level 1 | CloudWatch |
| 5.9 | Ensure AWS Config configuration changes are monitored | Manual | Level 1 | CloudWatch |
| 5.10 | Ensure security group changes are monitored | Manual | Level 1 | CloudWatch |
| 5.11 | Ensure Network Access Control List (NACL) changes are monitored | Manual | Level 1 | CloudWatch |
| 5.12 | Ensure changes to network gateways are monitored | Manual | Level 1 | CloudWatch |
| 5.13 | Ensure route table changes are monitored | Manual | Level 1 | CloudWatch |
| 5.14 | Ensure VPC changes are monitored | Manual | Level 1 | CloudWatch |
| 5.15 | Ensure AWS Organizations changes are monitored | Manual | Level 1 | CloudWatch |
| 5.16 | Ensure AWS Security Hub is enabled | Automated | **Level 2** | Security Hub |

---

### 6 — Networking

#### 6.1 Elastic Compute Cloud (EC2)

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 6.1.1 | Ensure EBS volume encryption is enabled in all regions | Automated | Level 1 | EC2/EBS |
| 6.1.2 | Ensure CIFS access is restricted to trusted networks to prevent unauthorized access | Automated | Level 1 | EC2/SG |

#### 6.2–6.7 (VPC / Security Groups)

| Control ID | Title | Status | Profile | Service |
|------------|-------|--------|---------|---------|
| 6.2 | Ensure no Network ACLs allow ingress from 0.0.0.0/0 to remote server administration ports | Automated | Level 1 | VPC/NACL |
| 6.3 | Ensure no security groups allow ingress from 0.0.0.0/0 to remote server administration ports | Automated | Level 1 | EC2/SG |
| 6.4 | Ensure no security groups allow ingress from ::/0 to remote server administration ports | Automated | Level 1 | EC2/SG |
| 6.5 | Ensure the default security group of every VPC restricts all traffic | Automated | Level 1 | VPC/SG |
| 6.6 | Ensure routing tables for VPC peering are "least access" | Manual | Level 1 | VPC |
| 6.7 | Ensure that the EC2 Metadata Service only allows IMDSv2 | Automated | Level 1 | EC2 |

---

## Summary Counts

| Section | Controls | Automated | Manual |
|---------|----------|-----------|--------|
| 2 IAM | 21 | 14 | 7 |
| 3 Storage | 9 | 6 | 3 |
| 4 Logging | 9 | 6 | 3 |
| 5 Monitoring | 16 | 1 | 15 |
| 6 Networking | 9 | 7 | 2 |
| **Total** | **64** | **34** | **30** |

---

## Steampipe Query → CIS v6 Control Mapping

Use `control_ref` in `queries.json` extra_metadata to map to CIS control_id. Example mappings:

| control_ref (query) | CIS control_id | Title |
|---------------------|----------------|-------|
| s3-public-access | 3.1.4 | Ensure that S3 is configured with 'Block Public Access' enabled |
| s3-public-policy | 3.1.4 | (related: block public access covers policy) |
| rds-public | 3.2.3 | Ensure that RDS instances are not publicly accessible |
| iam-admin-policies | 2.15 | Ensure IAM policies that allow full "*:*" administrative privileges are not attached |

**Note:** CIS v6 does **not** include S3 versioning or S3 default encryption as separate controls. Those may map to internal policies or older CIS versions. Use `config/cis_v6_controls.yaml` for full mapping.

---

## References

- **PDF:** `docs/CIS_Amazon_Web_Services_Foundations_Benchmark_v6.0.0.pdf`
- **CIS Workbench:** https://workbench.cisecurity.org
- **AWS Product Directory:** https://aws.amazon.com/products/
