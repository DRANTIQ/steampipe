# FedRAMP — Reference & Implementation Guide

**FedRAMP** authorizes cloud services for US federal use. Technical controls are **NIST SP 800-53** at Low/Moderate/High baselines.

---

## Official sources

| Document | Description | URL |
|----------|-------------|-----|
| **FedRAMP.gov** | Program overview, baselines | https://www.fedramp.gov/ |
| **NIST 800-53 Rev 5** | Underlying control catalog | https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final |
| **FedRAMP OSCAL baselines** | Moderate/High control selections | https://github.com/GSA/fedramp-automation |

---

## Implementation path for this platform

1. Implement **NIST 800-53** first (`nist/reference/README.md`).
2. Filter to **FedRAMP Moderate** baseline using GSA OSCAL profiles.
3. Register `framework_id: fedramp_moderate_aws` as a **view** over NIST controls (subset), not duplicate SQL.

AWS GovCloud patterns and boundary definitions are organizational — mostly manual.

Store PDFs under: `compliance-frameworks/fedramp/reference/`.
