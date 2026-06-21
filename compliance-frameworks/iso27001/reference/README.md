# ISO 27001 — Reference & Implementation Guide

**ISO/IEC 27001:2022** defines an Information Security Management System (ISMS). **Annex A** lists 93 controls (organizational + technical). The full standard is **paid**; public summaries exist from cloud vendors.

---

## Official sources

| Document | Description | How to obtain |
|----------|-------------|---------------|
| **ISO/IEC 27001:2022** | ISMS requirements + Annex A control list | https://www.iso.org/standard/82875.html (purchase) |
| **ISO/IEC 27002:2022** | Control implementation guidance | https://www.iso.org/standard/75652.html (purchase) |
| **ISO 27001 Annex A (overview)** | Control themes | Cloud provider compliance pages (free summaries) |

---

## Free mapping resources

| Resource | Use |
|----------|-----|
| [AWS ISO 27001 FAQ](https://aws.amazon.com/compliance/iso-27001-faqs/) | Which AWS services are in scope for AWS’s cert (not your account config) |
| [Azure ISO 27001](https://learn.microsoft.com/en-us/azure/compliance/offerings/offering-iso-27001) | Same for Azure platform |
| **CIS Controls v8 → ISO 27001** | CIS publishes mapping spreadsheets |
| **Steampipe AWS Compliance mod** | `iso_27001` benchmark section | https://github.com/turbot/steampipe-mod-aws-compliance |
| **Prowler** | ISO 27001 themed checks | https://github.com/prowler-cloud/prowler |

---

## Automatable vs manual (typical split)

| Annex A theme | Examples | Steampipe? |
|---------------|----------|------------|
| A.5 Organizational | Policies, roles | **Manual** |
| A.8 Asset management | Inventory | **Partial** — inventory queries |
| A.8.24 Cryptography | Encryption at rest | **Yes** — S3/RDS/EBS queries |
| A.8.15 Logging | CloudTrail, log retention | **Yes** |
| A.8.2 Privileged access | Root MFA, admin roles | **Yes** |
| A.8.19 Installation on networks | Security groups, NACLs | **Yes** |

Expect ~40–60% of Annex A to be **Manual** or **policy evidence** in a GRC tool; automate the cloud-config subset via CIS/NIST-derived SQL.

---

## Implementation in cloud-compliance-engine

1. `config/iso27001_aws_controls.yaml` — use Annex A IDs (e.g. `A.8.15`) as `control_id`.
2. Reuse CIS AWS queries where they map 1:1; add ISO-specific titles in YAML.
3. `queries/iso27001_aws_queries.json` — port from Steampipe mod or duplicate CIS SQL with ISO metadata.
4. Register `framework_id: iso27001_aws` in catalog.yaml.

Place purchased ISO PDFs in: `compliance-frameworks/iso27001/reference/`.
