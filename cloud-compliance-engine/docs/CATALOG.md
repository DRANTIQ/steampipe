# Query and Control Catalog

Where compliance rules are defined and how Stage 1 and Stage 2 stay in sync.

---

## Single source of truth

```
data/queries.json          ← Steampipe SQL + evaluation metadata
        │
        ├── scripts/apply_queries_document.py  →  public.queries (Stage 1 runs SQL)
        │
        └── rule_engine/registry.py            →  RuleRegistry (Stage 2 evaluates)

config/cis_v6_controls.yaml  →  compliance.controls (UI text, severity, remediation)
        │
        └── app/scripts/seed_catalog.py
```

**There is no second queries JSON inside `cloud-compliance-engine/`.**

---

## Query entry shape (`data/queries.json`)

Each compliance query:

```json
{
  "name": "cis_5_16_security_hub_enabled",
  "version": "1.0",
  "provider": "aws",
  "plugin": "aws",
  "query_text": "select region from aws_region where ...",
  "active": true,
  "extra_metadata": {
    "category": "compliance",
    "framework_id": "cis_aws_v6",
    "framework": "CIS AWS Foundations Benchmark v6.0.0",
    "control_id": "5.16",
    "control_ref": "security-hub-enabled",
    "pass_rule": "zero_rows",
    "required_columns": ["region"],
    "natural_key": "region"
  }
}
```

| Field | Stage 1 | Stage 2 |
|-------|---------|---------|
| `query_text` | ✅ Executed by Steampipe | ❌ Not used |
| `control_ref` | In snapshot metadata | ✅ Rule lookup key |
| `pass_rule` | In snapshot metadata | ✅ PASS/FAIL logic |
| `required_columns` | In snapshot metadata | ✅ Evidence fields |
| `category` | Filters scan/bulk | ✅ Worker filter |

---

## Control catalog (`config/cis_v6_controls.yaml`)

Human-facing definitions for UI and reports:

```yaml
controls:
  - control_id: "5.16"
    title: "Ensure AWS Security Hub is enabled"
    service: Security Hub
    severity: High
    profile: Level 2
    assessment_status: Automated
    control_ref: security-hub-enabled
```

Manual controls (no Steampipe query) are listed here but have no matching query in `data/queries.json`.

---

## Seed configuration (`config/catalog.yaml`)

```yaml
frameworks:
  - framework_id: cis_aws_v6
    provider: aws
    category: compliance
    controls_path: config/cis_v6_controls.yaml
    rules_source: data/queries.json
    framework_title: "CIS AWS Foundations Benchmark v6.0.0"
    version_name: "6.0.0"
```

---

## Sync workflow (after any catalog change)

```powershell
# From repo root (Docker with volume mount)
docker compose -f docker-compose.remote.yml run --rm -v "${PWD}:/app" -e PYTHONPATH=/app/cloud-compliance-engine:/app api python scripts/setup_compliance.py
```

This runs:

1. `alembic upgrade head`
2. `apply_queries_document.py` — updates `public.queries`
3. `seed_catalog` — updates `compliance.controls` + `rule_versions` hash

---

## CIS v6 scope (commercial v1)

- **Framework:** `cis_aws_v6` only
- **Automated checks:** ~35 queries with `category: compliance` and `cis_*` names
- **Claim:** aligned with CIS AWS Foundations v6.0.0 automated subset — not full benchmark certification

---

## Related

- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) — add a new control
- [../../docs/QUERIES_AND_COMPLIANCE_DESIGN.md](../../docs/QUERIES_AND_COMPLIANCE_DESIGN.md) — licensing (no Powerpipe AGPL in pipeline)
