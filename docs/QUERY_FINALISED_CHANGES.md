# Finalised Changes for Query Storage

Concrete list of changes to implement (minimal, ship-fast base). No Powerpipe/AGPL content; Steampipe SQL only.

---

## 1. Schema / migration

| # | Change | Details |
|---|--------|---------|
| 1 | Add `content_hash` to `queries` | `content_hash VARCHAR(64) NULL` — SHA-256 of normalized `query_text` (e.g. strip trailing semicolons/whitespace). For integrity and future dedup. |
| 2 | Add index on `(provider, plugin)` | `CREATE INDEX ix_queries_provider_plugin ON queries (provider, plugin);` |
| 3 | Add partial index for active queries | `CREATE INDEX ix_queries_active_not_deleted ON queries (name) WHERE deleted_at IS NULL AND active = true;` (or equivalent for your default listing). |

**No new tables.** No `tenant_id` on `queries` unless you decide you need tenant-scoped queries (then add nullable `tenant_id`).

---

## 2. Model (`src/models/query.py`)

| # | Change | Details |
|---|--------|---------|
| 1 | Add `content_hash` | `content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)` |
| 2 | (Optional) Index on `provider, plugin` | In SQLAlchemy: ensure migration adds it; model can rely on migration. |

---

## 3. `extra_metadata` conventions

Use these keys in `extra_metadata` (no new columns; JSONB only):

| Key | Type | Purpose |
|-----|------|---------|
| `framework` | string | e.g. `"CIS AWS Foundations 4.0"`, `"SOC2"` — for filtering/reporting. |
| `control_id` or `control_ref` | string | e.g. `"1.2.3"` — our label for control alignment (no AGPL content). |
| `source` | string | `"manual"` \| `"import"` \| `"template"` — provenance. |
| `source_ref` | string | Optional URL or id for import source. |
| `import_batch_id` | string | Optional; link queries from same import. |
| `required_columns` | array of strings | For compliance queries: column names the extract step and control engine must preserve (see [REAL_SAAS_DATA_FLOW_AND_COLUMNS.md](REAL_SAAS_DATA_FLOW_AND_COLUMNS.md)). |
| `pass_rule` | string | e.g. `zero_rows` (pass when query returns no rows). Used by CIS/control evaluation. |

Document these in API docs or OpenAPI so consumers know the shape.

---

## 4. Application logic (on create/update of Query)

| # | Change | Details |
|---|--------|---------|
| 1 | Set `content_hash` on save | When saving/updating a query, compute SHA-256 of normalized `query_text` and set `content_hash`. |
| 2 | (Optional) Validation | Before first run or on save: optional syntax check or allowlist of tables (e.g. only `aws_*`) — implement when you’re ready. |

---

## 5. What we do *not* do

- Do **not** add Powerpipe mod content or run Powerpipe in the service.
- Do **not** store HCL or benchmark definitions in the DB.
- Do **not** change execution path: worker keeps using Steampipe + `query_text` only.

---

## 6. Checklist summary

- [ ] Migration: add `content_hash`, index `(provider, plugin)`, partial index (active + not deleted).
- [ ] Model: add `content_hash` column.
- [ ] On create/update: compute and set `content_hash` (normalized SQL).
- [ ] Document `extra_metadata` keys (`framework`, `control_id`, `source`, `source_ref`, `import_batch_id`) in API/docs.

That’s the finalised set for the minimal base.
