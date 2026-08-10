# SOC 2 — Reference & Implementation Guide

SOC 2 is based on **AICPA Trust Services Criteria (TSC)**, not cloud API benchmarks. Most “SOC 2 compliance products” combine **organizational policies** with **technical checks** mapped to criteria like CC6 (Logical Access) and CC7 (System Operations).

---

## Official sources

| Document | Description | How to obtain |
|----------|-------------|---------------|
| **Trust Services Criteria** | CC1–CC9 control language | [AICPA SOC 2 resources](https://www.aicpa.org/resources/landing/system-and-organization-controls-soc-2) |
| **SOC 2 Type II report** | Your auditor’s output | From your CPA firm after audit (not a download) |
| **SOC 2 for Service Organizations** | Implementation guide | AICPA / auditor templates |

There is **no free PDF** equivalent to CIS with Steampipe SQL for every SOC 2 criterion.

---

## Best technical control sources (for Steampipe / this platform)

Use these to build `queries/*.json` and map to SOC 2 criteria in YAML:

| Source | Content | Link |
|--------|---------|------|
| **Steampipe AWS Compliance mod** | `soc_2` benchmark with SQL controls | https://github.com/turbot/steampipe-mod-aws-compliance |
| **Prowler** | SOC 2 checks per cloud | https://github.com/prowler-cloud/prowler |
| **AWS Audit Manager** | Managed SOC 2 framework | AWS Console → Audit Manager |
| **Azure Policy / Defender** | SOC-aligned initiatives | Microsoft Learn compliance offerings |

---

## Typical TSC → cloud mapping (examples)

| TSC | Theme | Example technical check (automatable) |
|-----|-------|--------------------------------------|
| CC6.1 | Logical access | Root MFA enabled, no root access keys |
| CC6.6 | Credentials | IAM password policy, access key rotation |
| CC6.7 | Transmission | S3 bucket encryption, TLS on ALB |
| CC7.2 | Monitoring | CloudTrail enabled, log validation |
| CC7.3 | Evaluation | GuardDuty / Security Hub enabled |

Many CC criteria (CC1 governance, CC2 communication) are **Manual** in your engine — document in YAML with `assessment_status: Manual`.

---

## Implementation in cloud-compliance-engine

1. Create `config/soc2_aws_controls.yaml` with `control_id` = TSC reference (e.g. `CC6.1`) + `control_ref` for automated checks.
2. Port SQL from Steampipe mod into `queries/soc2_aws_queries.json`.
3. Add entry to `cloud-compliance-engine/config/catalog.yaml`:
   ```yaml
   - framework_id: soc2_aws
     provider: aws
     category: compliance
     controls_path: config/soc2_aws_controls.yaml
     rules_path: queries/soc2_aws_queries.json
     framework_title: "SOC 2 Trust Services Criteria (AWS technical)"
     version_name: "2017"
   ```
4. Run `python -m app.scripts.seed_catalog`.

Store any AICPA PDFs you purchase under this folder: `compliance-frameworks/soc2/reference/`.
