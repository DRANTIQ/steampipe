# Split: Cloud Compliance Engine → Separate Repo

**Decision:** Compliance engine moves to its own repository. Steampipe platform stays in `steampipe` (Stage 1).

**Status:** New repo created at `cloud-compliance-engine/` (sibling to `steampipe`).

See **[../cloud-compliance-engine/README.md](../cloud-compliance-engine/README.md)** and **[../cloud-compliance-engine/contracts/STAGE1_INTEGRATION.md](../cloud-compliance-engine/contracts/STAGE1_INTEGRATION.md)**.

---

## Target layout

### Repo 1: `steampipe` (Stage 1 — collection)

```
steampipe/
├── src/                    # API, workers, scheduler
├── data/queries.json       # SQL + metadata (Stage 1 runs SQL)
├── alembic/                # Migrations 001–002 only (public schema) after split
├── docker-compose.remote.yml   # api, worker, scheduler only
└── docs/
```

### Repo 2: `cloud-compliance-engine` (Stage 2 — judgment)

```
cloud-compliance-engine/
├── app/                    # API, worker, services
├── config/                 # cis_v6_controls.yaml, catalog.yaml
├── alembic/                # Migrations 003–006 (compliance schema)
├── data/queries.json       # Optional copy for seed_catalog offline
├── docker-compose.yml      # compliance-api + compliance-worker
├── docs/
└── contracts/              # Integration spec with Stage 1
    └── STAGE1_INTEGRATION.md
```

---

## Integration contracts (unchanged)

Both repos share **runtime contracts**, not code imports:

| Contract | Owner | Consumer |
|----------|--------|----------|
| Postgres `public.execution_*` | Stage 1 | Compliance (read) |
| Postgres `compliance.*` | Compliance | Compliance (write) |
| Redis `steampipe:job_completed` | Stage 1 publish | Compliance worker consume |
| Bronze JSON schema v1.0 | Stage 1 write | Compliance read |
| `public.queries.extra_metadata` | Stage 1 seed | Compliance rules (primary) |

See [cloud-compliance-engine/contracts/STAGE1_INTEGRATION.md](../cloud-compliance-engine/contracts/STAGE1_INTEGRATION.md) (created at cutover).

---

## Cutover checklist

### Phase A — Prepare (in monorepo, before split)

- [x] Compliance config standalone (no `import src.config`)
- [x] Snapshot path resolution works from any cwd
- [ ] Copy alembic `003`–`006` into `cloud-compliance-engine/alembic/`
- [ ] Add `cloud-compliance-engine/docker-compose.yml`
- [ ] Add `contracts/STAGE1_INTEGRATION.md`
- [ ] Compliance `.env.example` has all required vars (no parent repo)

### Phase B — Create new repo

```powershell
# 1. Create empty GitHub repo: cloud-compliance-engine

# 2. Export folder history (optional) or fresh copy
cd C:\Users\devar\OneDrive\Documents\GitHub
git clone https://github.com/YOU/steampipe.git steampipe-export
cd steampipe-export
git subtree split --prefix=cloud-compliance-engine -b compliance-only
cd ..
git init cloud-compliance-engine
cd cloud-compliance-engine
git pull ../steampipe-export compliance-only
git remote add origin https://github.com/YOU/cloud-compliance-engine.git
git push -u origin main
```

**Simpler (no history):** copy `cloud-compliance-engine/` folder → new repo → commit.

### Phase C — Clean steampipe repo

- [ ] Remove `cloud-compliance-engine/` from monorepo (or git submodule)
- [ ] Remove compliance services from `docker-compose.remote.yml`
- [ ] Trim alembic to `001`–`002` only (compliance migrations live in new repo)
- [ ] Update `docs/COMPLIANCE_PLATFORM.md` with link to external repo
- [ ] Keep `scripts/setup_compliance.py` as thin wrapper OR delete and document two setup flows

### Phase D — Deploy both

| Service | Repo | Port |
|---------|------|------|
| steampipe-api | steampipe | 8000 |
| steampipe-worker | steampipe | — |
| compliance-api | cloud-compliance-engine | 8001 |
| compliance-worker | cloud-compliance-engine | — |

Same `.env` values: `DATABASE_URL`, `REDIS_URL`, `LOCAL_STORAGE_PATH` / S3.

---

## Environment (compliance repo)

Standalone `.env` — no parent repo:

```env
DATABASE_URL=postgresql://...
REDIS_URL=rediss://...
COMPLIANCE_QUEUE_KEY=steampipe:job_completed
USE_LOCAL_STORAGE=true
LOCAL_STORAGE_PATH=/data/snapshots
DEFAULT_TENANT_ID=

# Optional: seed from file when public.queries empty
# CATALOG_QUERIES_PATH=./data/queries.json
```

**Rules source of truth after split:** `public.queries` in shared Postgres (Stage 1 runs `apply_queries_document.py`).

Compliance `seed_catalog` only needs `data/queries.json` if bootstrapping a fresh DB without Stage 1.

---

## Database migrations split

| Migration | Schema | Repo after split |
|-----------|--------|------------------|
| 001, 002 | `public` | steampipe |
| 003–006 | `compliance` | cloud-compliance-engine |

Both repos point at the **same Postgres**. Run migrations in order:

```powershell
# steampipe repo
alembic upgrade head

# cloud-compliance-engine repo
alembic upgrade head
```

Use separate `alembic_version` tables OR single table with coordinated revision IDs (recommended: **separate alembic in each repo**, compliance revisions start at `001` mapping to old `003` content).

---

## Monorepo transition period

Until cutover, both can coexist:

- Set `COMPLIANCE_STANDALONE=true` in compliance `.env` to skip loading parent `.env`
- Or leave unset for monorepo convenience (loads parent `.env` for shared DB/Redis)

---

## Submodule alternative (optional)

Keep one clone, two repos:

```powershell
git submodule add https://github.com/YOU/cloud-compliance-engine.git cloud-compliance-engine
```

Use if you want one `docker compose up` from steampipe but separate git history.

---

## Related

- [IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md) — task **T-038**
- [COMPLIANCE_PLATFORM.md](COMPLIANCE_PLATFORM.md)
