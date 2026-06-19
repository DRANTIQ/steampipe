# How to Save Queries — Architect / Senior DB Engineer Ideas

Structured **options and trade-offs** for storing and governing queries. Pick what fits the product; no need to do everything. Complements [QUERIES_AND_COMPLIANCE_DESIGN.md](QUERIES_AND_COMPLIANCE_DESIGN.md).

---

## 1. Identity and Versioning

| Idea | What | Why |
|------|------|-----|
| **Keep name + version (current)** | One row per logical query; `(name, version)` unique. | Simple, clear. Good for "CIS 1.2.3 v1.0" style. |
| **Semantic versioning** | Store version as `major.minor.patch`; treat `major` as breaking, `minor` as additive. | Enables "run latest 1.x" or "pin to 1.2.0". |
| **Draft vs published** | Add `status: draft \| published`. Only published are runnable by schedules/bulk. | Safe editing; avoid running half-finished SQL. |
| **Immutable published** | When status → published, copy row to a "revisions" table or new version; never overwrite. | Audit trail, rollback, "what did we run on date X". |

**Recommendation:** Start with name + version + optional `status`. Add revision history when you need audit/rollback.

---

## 2. Where Query Rows Live (Tenancy)

| Idea | What | Why |
|------|------|-----|
| **Global query library (current)** | No `tenant_id` on `queries`; schedules/jobs link tenant → query. | One set of queries for all tenants; easy updates. |
| **Tenant-scoped queries** | Add `tenant_id` to `queries`; optional `tenant_id = null` = platform template. | Tenants can have private/custom queries; platform provides templates. |
| **Hybrid** | Platform queries (read-only, `tenant_id null`) + tenant overrides (tenant_id set). Resolve by "tenant override else platform". | Best of both: standard library + tenant customization. |

**Recommendation:** If you need per-tenant custom queries, add `tenant_id` (nullable) and treat `null` as platform. If all tenants share the same list, keep global.

---

## 3. Storing the SQL Itself

| Idea | What | Why |
|------|------|-----|
| **Inline `query_text` (current)** | SQL in same row. | Simple, one read, no extra storage. |
| **Out-of-line for large SQL** | Store body in object storage (S3); DB has `query_body_path` + `content_hash`. | Keeps table small; good if you have huge or many queries. |
| **Content-addressed** | Hash of `query_text`; store hash in DB. Dedupe: same SQL → same hash, reuse. | Saves space if same SQL used in many "query" rows (e.g. same check, different metadata). |
| **Revision table** | `query_versions` or `query_revisions`: `query_id`, `version_ordinal`, `query_text`, `created_at`. Main table points at "current" version. | Full history; diff/rollback; "what changed". |

**Recommendation:** Stay inline unless you have thousands of queries or very large SQL. Add `content_hash` (e.g. SHA-256 of normalized SQL) for dedup and integrity; optional later.

---

## 4. Metadata and Discovery

| Idea | What | Why |
|------|------|-----|
| **`extra_metadata` only (current)** | JSONB for framework, control_id, tags, etc. | Flexible; no schema change. |
| **Hot-path columns** | Promote frequently filtered fields: `framework`, `control_id`, `category` (e.g. compliance, cost, security). | Fast filters and reporting without JSONB predicates. |
| **Tags array** | `tags: text[]` or JSONB array for "CIS", "SOC2", "ec2", "iam". | Easy "all CIS queries", "all cost queries". |
| **Provenance** | `source: manual \| import \| template`, `source_ref` (URL or id), `import_batch_id`. | Traceability; "these 50 came from import X". |

**Recommendation:** Use `extra_metadata` for now; add indexed columns only for fields you filter/sort on in hot paths (e.g. framework when building compliance dashboards).

---

## 5. Reuse and Composition

| Idea | What | Why |
|------|------|-----|
| **One query = one SQL (current)** | Single `query_text` per row. | Simple execution model. |
| **Parameterized queries** | Template with placeholders (e.g. `:account_id`, `:region`); bind at execution time. | One template, many runs; avoid storing near-duplicate SQL. |
| **Query packs / bundles** | Grouping: "CIS 4.0" = set of query IDs. Store as `query_packs` table or `extra_metadata.pack_id`. | Run "all CIS" as one unit; report by pack. |
| **Fragments / CTEs** | Separate table for reusable SQL fragments; compose at save or at runtime. | DRY; harder to implement and debug. |

**Recommendation:** Keep one SQL per query. Add "query pack" or "query group" when you need "run these N queries together" (e.g. for CIS/SOC2 sets).

---

## 6. Lifecycle and Governance

| Idea | What | Why |
|------|------|-----|
| **Soft delete (current)** | `deleted_at`; filter out in API. | Safe delete; can restore. |
| **Deprecation** | `deprecated_at`, `replaced_by_query_id`. | Guide users to new version; keep history. |
| **Approval workflow** | Draft → submit → approved → published. Optional `approved_by`, `approved_at`. | Compliance/change control. |
| **Validation on save** | Check syntax (e.g. parse SQL); optionally allowlist tables (e.g. only `aws_*`). | Catch errors early; prevent dangerous or off-limits SQL. |

**Recommendation:** Keep soft delete. Add deprecation fields when you version heavily. Validation (syntax or allowlist) is valuable before first run.

---

## 7. Indexing and Performance

| Idea | What | Why |
|------|------|-----|
| **Index (provider, plugin)** | Composite index. | "All AWS queries", "all queries for turbot/aws". |
| **Index (name)** | You have it. | Lookup by name. |
| **Partial index** | e.g. `WHERE deleted_at IS NULL AND active = true`. | Smaller index; fast for "active queries" list. |
| **Partitioning** | By `tenant_id` or `created_at` if table grows to millions. | Maintenance and query performance at scale. |

**Recommendation:** Add composite index `(provider, plugin)` if you list/filter by provider/plugin. Partial index on "active and not deleted" is a win for the default listing.

---

## 8. Summary: Minimal vs Strong Base

- **Minimal (ship fast):** Keep current schema; add optional `content_hash`, use `extra_metadata` for framework/control_ref/source; add index on `(provider, plugin)` and partial index for active queries.
- **Strong base (audit + multi-tenant):** Above + `tenant_id` (nullable), `status` (draft/published), `query_revisions` or immutable versions, deprecation fields, and optionally query packs table for "run set X".

Choose based on whether you need tenant-specific queries, strict audit, and pack-based execution soon.
