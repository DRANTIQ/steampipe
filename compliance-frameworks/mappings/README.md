# Cross-Framework Mappings

Many cloud technical checks are **identical** across frameworks; only the **control ID and audit language** change.

---

## One SQL query, multiple frameworks

Example: “Root account should not have access keys”

| Framework | Control ID | Same Steampipe SQL? |
|-----------|------------|---------------------|
| CIS AWS v6/v7 | 2.3 | Yes |
| SOC 2 | CC6.1 | Yes |
| ISO 27001 | A.8.2 | Yes |
| NIST 800-53 | AC-2, IA-2 | Yes |
| PCI DSS | 7.2, 8.2 | Partial overlap |

**Data model approach:**

```yaml
# One rule in queries JSON
control_ref: iam-root-access-keys

# Multiple framework entries in controls YAML or framework_control_mappings table
- framework_id: cis_aws_v6
  control_id: "2.3"
- framework_id: soc2_aws
  control_id: "CC6.1"
```

Run Steampipe **once** per query; evaluate **once** per snapshot; map result to **many framework control IDs**.

---

## Recommended mapping sources

| Mapping | Source |
|---------|--------|
| CIS Controls v8 ↔ ISO 27001 | https://www.cisecurity.org/ — CIS Controls mapping documents |
| CIS AWS ↔ NIST 800-53 | Turbot Steampipe mod tags on each control |
| AWS Audit Manager | Built-in cross-framework control mapping |
| **OSCAL** | NIST maintains machine-readable mappings | https://github.com/usnistgov/oscal-content |

---

## Steampipe mod as Rosetta Stone

The Turbot **steampipe-mod-aws-compliance** mod tags each control with framework references:

```
github.com/turbot/steampipe-mod-aws-compliance
  ├── benchmark cis_v150
  ├── benchmark soc_2
  ├── benchmark nist_800_53_rev_5
  ├── benchmark pci_dss_v321
  ├── benchmark hipaa_security_rule_164_308
  └── benchmark iso_27001
```

When adding SOC/ISO/NIST:

1. Pick a control in the mod.
2. Copy its SQL query.
3. Add YAML entries for each framework you support.
4. Avoid maintaining 5 copies of the same SQL — use shared `control_ref`.

See also: [`docs/POWERPIPE_FOLDER_GUIDE.md`](../../docs/POWERPIPE_FOLDER_GUIDE.md).

---

## Implementation priority matrix

| Priority | Framework | Why |
|----------|-----------|-----|
| 1 | CIS AWS Foundations v6/v7 | PDFs on disk; partial code exists |
| 2 | NIST 800-53 | Free, FedRAMP/SOC overlap, Steampipe mod ready |
| 3 | SOC 2 (technical subset) | Customer demand; map from CIS/NIST |
| 4 | CIS Azure Foundations | PDF on disk; needs Azure plugin queries |
| 5 | ISO 27001 | Mostly mapping layer over CIS/NIST |
| 6 | PCI / HIPAA | Industry-specific customers |
| 7 | CIS service benchmarks (storage, DB, EKS) | Depth after foundations |
