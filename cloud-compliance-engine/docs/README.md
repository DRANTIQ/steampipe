# Cloud Compliance Engine — Documentation

Start here. All current docs live under this folder.

---

## Read in this order

| # | Document | Who | Purpose |
|---|----------|-----|---------|
| 1 | [RUNBOOK.md](../RUNBOOK.md) | Ops / you | Setup, run scans, troubleshoot |
| 2 | [ARCHITECTURE.md](ARCHITECTURE.md) | Everyone | End-to-end flow, data layers, events |
| 3 | [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) | Developers | What each file/folder does |
| 4 | [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Developers | Code walkthrough, extend controls |
| 5 | [API.md](API.md) | Frontend / integrators | REST endpoints for UI |
| 6 | [CATALOG.md](CATALOG.md) | Product / compliance | Query catalog + control definitions |

---

## Repo-level docs (Stage 1 + platform)

| Document | Location |
|----------|----------|
| CIS scan (Steampipe) | [`../../docs/CIS_SCAN_RUNBOOK.md`](../../docs/CIS_SCAN_RUNBOOK.md) |
| Platform overview | [`../../docs/COMPLIANCE_PLATFORM.md`](../../docs/COMPLIANCE_PLATFORM.md) |
| **Prioritized task list** | [`../../docs/IMPLEMENTATION_ROADMAP.md`](../../docs/IMPLEMENTATION_ROADMAP.md) |
| Licensing / SQL ownership | [`../../docs/QUERIES_AND_COMPLIANCE_DESIGN.md`](../../docs/QUERIES_AND_COMPLIANCE_DESIGN.md) |

---

## Archive (historical — do not use for implementation)

Old design specs and outdated path layouts:

- [`archive/`](archive/) — IMPLEMENTATION_PROMPT, PROMPT, DESIGN, early architecture docs

---

## Reference (not executed at runtime)

- [`../reference/cis_v6.pp`](../reference/cis_v6.pp) — Powerpipe benchmark reference (AGPL; not used in pipeline)
- [CIS_V6_REFERENCE.md](CIS_V6_REFERENCE.md) — Control ID notes
