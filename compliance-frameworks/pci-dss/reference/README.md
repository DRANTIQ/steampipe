# PCI DSS — Reference & Implementation Guide

**Payment Card Industry Data Security Standard** — required if you store, process, or transmit cardholder data (CHD).

---

## Official sources

| Document | Description | URL |
|----------|-------------|-----|
| **PCI DSS v4.0** | Full standard | https://www.pcisecuritystandards.org/document_library/ (free registration) |
| **PCI DSS v4.0 Summary of Changes** | Migration from v3.2.1 | Same portal |
| **AWS PCI DSS** | Shared responsibility / scope | https://aws.amazon.com/compliance/pci-dss-level-1-faqs/ |

---

## Technical check sources

| Source | Notes |
|--------|-------|
| **Steampipe mod** | `pci_dss_v321` benchmark (check mod for v4 updates) | https://github.com/turbot/steampipe-mod-aws-compliance |
| **Prowler** | PCI section | https://github.com/prowler-cloud/prowler |
| **AWS Config** | PCI conformance pack | AWS Config → Conformance packs |

PCI requirements (e.g. Req 1 firewall, Req 2 defaults, Req 10 logging) map well to Steampipe SQL on security groups, IAM, CloudTrail.

---

## Scope warning

PCI scope depends on **network segmentation** and **what touches CHD** — automation covers **technical** requirements; SAQ/roster/scope docs remain manual.

Implementation: `framework_id: pci_dss_aws` in catalog when ready.

Store PDFs under: `compliance-frameworks/pci-dss/reference/`.
