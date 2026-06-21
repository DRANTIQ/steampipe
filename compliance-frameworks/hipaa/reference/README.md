# HIPAA — Reference & Implementation Guide

**HIPAA Security Rule** (45 CFR Part 164) applies to covered entities and business associates handling PHI.

---

## Official sources

| Document | Description | URL |
|----------|-------------|-----|
| **HIPAA Security Rule** | Administrative, physical, technical safeguards | https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html |
| **NIST SP 800-66 Rev 2** | HIPAA Security Rule implementation guide | https://csrc.nist.gov/publications/detail/sp/800-66/rev-2/final |
| **AWS HIPAA** | BAA-eligible services | https://aws.amazon.com/compliance/hipaa-compliance/ |

---

## Technical check sources

| Source | Notes |
|--------|-------|
| **Steampipe mod** | `hipaa_security_rule_164_308` and related benchmarks | https://github.com/turbot/steampipe-mod-aws-compliance |
| **Prowler** | HIPAA checks | https://github.com/prowler-cloud/prowler |

Many HIPAA safeguards (risk analysis, workforce training) are **Manual**. Automate: encryption, access control, audit logging, backup — overlap heavily with CIS/NIST.

Implementation: `framework_id: hipaa_aws` when needed.

Store reference PDFs under: `compliance-frameworks/hipaa/reference/`.
