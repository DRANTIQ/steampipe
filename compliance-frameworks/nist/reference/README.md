# NIST — Reference & Implementation Guide

NIST publications are **free** and are the best source for **control IDs** that map to cloud technical checks. FedRAMP and many enterprise programs inherit **NIST SP 800-53**.

---

## Official sources (free)

| Document | Description | URL |
|----------|-------------|-----|
| **NIST Cybersecurity Framework 2.0** | Functions: Govern, Identify, Protect, Detect, Respond, Recover | https://www.nist.gov/cyberframework |
| **NIST SP 800-53 Rev 5** | Security and privacy controls catalog | https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final |
| **NIST SP 800-53 Rev 5 (OSCAL)** | Machine-readable control catalog | https://github.com/usnistgov/oscal-content |
| **NIST SP 800-171 Rev 3** | Protecting CUI (defense supply chain) | https://csrc.nist.gov/publications/detail/sp/800-171/rev-3/final |

Download PDFs/XML into this folder when needed.

---

## Cloud-native implementations

| Source | Content |
|--------|---------|
| **Steampipe mod** | `nist_800_53_rev_5` benchmark | https://github.com/turbot/steampipe-mod-aws-compliance |
| **AWS Config** | Conformance pack `Operational-Best-Practices-for-NIST-800-53-rev-5` | AWS Config console |
| **Prowler** | NIST 800-53 / 800-171 checks | https://github.com/prowler-cloud/prowler |
| **Security Hub** | NIST CSF standard | AWS Security Hub → Standards |

---

## Why NIST fits this platform well

- Control IDs are stable (`AC-2`, `AU-2`, `SC-7`, …)
- OSCAL JSON enables future automation of control metadata import
- Heavy overlap with CIS AWS Foundations — many queries can be **shared** with different `framework_id` in YAML

---

## Implementation in cloud-compliance-engine

1. `config/nist_800_53_aws_controls.yaml` — `control_id: "AC-2"`, map `control_ref` to Steampipe SQL.
2. `queries/nist_800_53_aws_queries.json` — port from Turbot mod or AWS Config rule logic.
3. Catalog entry: `framework_id: nist_800_53_aws`.

Optional: import OSCAL from `usnistgov/oscal-content` for titles/descriptions; keep SQL in your queries JSON.

Store PDFs under: `compliance-frameworks/nist/reference/`.
