# Adding New Frameworks, Providers, and Categories

So that **adding future versions, providers (e.g. Azure, GCP), and categories (e.g. cost optimization)** is easy, everything is driven by **config + catalog**. No code change is required to add a new framework—only new data and one catalog entry.

---

## 1. What You Need (Required Data)

For each framework you need:

| Asset | Purpose | Format |
|-------|--------|--------|
| **Control definitions** | Titles, severity, remediation, control_id, control_ref (for automated) | YAML (see below) |
| **Rule definitions** | Queries + pass_rule + required_columns for evaluation | JSON (see below) |
| **Catalog entry** | Links framework_id, provider, category to the files | `config/catalog.yaml` |

All of this lives under `cloud-compliance-engine/` (or paths you reference from the catalog).

---

## 2. Control Definitions YAML

- **Path:** e.g. `config/cis_v6_controls.yaml` or `config/cost_optimization_aws_controls.yaml`
- **Structure:**

```yaml
framework: "Human-readable framework name"
framework_version: "6.0.0"

controls:
  - control_id: "2.3"
    title: "Ensure no root user access keys"
    service: IAM
    severity: Critical   # Critical | High | Medium | Low
    profile: Level 1
    assessment_status: Automated   # or Manual
    control_ref: iam-root-access-keys   # required if Automated; links to rules JSON
    remediation: "Optional steps"
    description: "Optional"
```

- **Rules:** `control_id` must be unique within the framework. For automated controls, `control_ref` must match a rule in the rules JSON.

---

## 3. Rule definitions (queries)

- **Path:** `data/queries.json` at **repo root** (single source for Stage 1 SQL and Stage 2 evaluation)
- Add entries with `extra_metadata.category: compliance` and your `framework_id`

```json
{
  "name": "cis_2_3_iam_root_access_keys",
  "query_text": "select ... from aws_...",
  "extra_metadata": {
    "category": "compliance",
    "framework_id": "cis_aws_v6",
    "control_id": "2.3",
    "control_ref": "iam-root-access-keys",
    "pass_rule": "zero_rows",
    "required_columns": ["account_id"]
  }
}
```

- **Rules:** `control_ref` must match the YAML’s `control_ref`. Evaluation uses `pass_rule` + `required_columns` (SQL runs in Stage 1 only).

See [CATALOG.md](CATALOG.md) for the full sync workflow.

---

## 4. Catalog entry

Edit **`config/catalog.yaml`**:

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

- **rules_source:** Path relative to **repo root** (not `cloud-compliance-engine/`)

---

## 5. Load Everything Into the DB (Seed)

After adding or changing YAML, JSON, or the catalog:

```bash
python scripts/setup_compliance.py
```

Or manually:

```bash
alembic upgrade head
python scripts/apply_queries_document.py
PYTHONPATH=cloud-compliance-engine python -m app.scripts.seed_catalog
```

- This reads **every** framework in `config/catalog.yaml`, loads the corresponding controls YAML and rules JSON, and upserts:
  - **compliance.framework_versions** (framework_id, version_name, provider, category)
  - **compliance.controls** (control_id, title, severity, remediation, provider, category, …)
  - **compliance.rule_versions** (one row per framework with hash of rules)
- So **all data** for frameworks you list in the catalog is in the DB after this run.

---

## 6. Checklist: Adding a New Framework / Version / Provider / Category

1. **Add control definitions**  
   Create or edit a YAML under `config/` with `framework`, `framework_version`, and `controls` (each with `control_id`, `title`, `severity`, `control_ref` if automated).

2. **Add queries**  
   Add compliance entries to `data/queries.json` with matching `control_ref` and `framework_id`.

3. **Register in catalog**  
   Add one entry under `frameworks` in `config/catalog.yaml` with `rules_source: data/queries.json`.

4. **Run setup**  
   `python scripts/setup_compliance.py`

5. **Use in API**  
   `GET /v1/controls?framework_id=...&provider=...&category=...` will return the new controls. Evaluation uses the same engine; point runs at the new `framework_id` and snapshot data that matches the new rules.

---

## 7. Cost Optimization / “And So On”

- **Same pattern:** Add a new `framework_id` (e.g. `cost_optimization_aws`) with `category: cost_optimization`, plus a controls YAML and a rules JSON. Add to the catalog and run the seed.
- **Snapshots:** Cost rules can use the same snapshot shape (e.g. Steampipe query output with `rows`) or a different one; the extract/evaluate pipeline stays the same, only the rules and control definitions change.
- **Future providers:** Same idea: add `config/cis_azure_v1_controls.yaml`, `queries/cis_azure_v1_queries.json`, and a catalog entry with `provider: azure`. Seed once; no extra code needed for “adding” beyond data and catalog.

This keeps **all required data** in one place (config + catalog) and makes **adding future versions, providers, and categories** a matter of adding files and one catalog block, then re-running the seed.
