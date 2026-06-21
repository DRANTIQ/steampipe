# Run Stage 1 with Remote Postgres and Redis (No Local DBs)

How to run the **Steampipe execution platform** using **remote** Postgres (e.g. Supabase) and Redis (e.g. Upstash) from `.env` — **without** starting local Postgres or Redis containers.

For the full Stage 1 reference (APIs, architecture, file structure), see **[STAGE1_FULL_GUIDE.md](STAGE1_FULL_GUIDE.md)**.

---

## Overview

| Component | Remote (from `.env`) | Local on your machine |
|-----------|----------------------|------------------------|
| Postgres  | Supabase, Railway, etc. | — |
| Redis     | Upstash, Railway, etc. | — |
| Snapshots | — | `./local/snapshots` (recommended for dev) |
| API       | — | `./scripts/run_api.sh` or Docker (`docker-compose.remote.yml`) |
| Worker    | — | `./scripts/run_worker.sh` + Steampipe, or Docker worker service |
| Scheduler | — | `./scripts/run_scheduler.sh` or Docker scheduler service |

```
Your Mac
├── API        ──► Supabase (Postgres) + Upstash (Redis)
├── Worker     ──► Supabase + Upstash + Steampipe + AWS + ./local/snapshots
└── Scheduler  ──► Supabase + Upstash

NO local Postgres container
NO local Redis container
```

---

## Important: do not use full `docker compose up`

The root **`docker-compose.yml`** is designed for an **all-in-one local stack**. It:

1. Starts **local** Postgres and Redis containers
2. **Overrides** `DATABASE_URL` and `REDIS_URL` inside api/worker/scheduler to point at those containers (`postgres:5432`, `redis:6379`)

If your `.env` has Supabase and Upstash URLs, **`docker compose up` will ignore them** for the app services.

**For remote DBs, use one of:**

- **Docker (all 3 processes):** `docker compose -f docker-compose.remote.yml up` — see [Option: Docker with remote DB](#option-docker-with-remote-db)
- **Local scripts:** Run API, worker, and scheduler with `./scripts/run_*.sh` (Python 3.12 venv)

Do **not** use plain `docker compose up` (root `docker-compose.yml`) — it starts local Postgres/Redis and overrides your URLs.

Stop any local stack before starting:

```bash
docker compose down
docker compose -f docker-compose.local.yml down
```

---

## Option: Docker with remote DB

Use **`docker-compose.remote.yml`** to run api + worker + scheduler in one command. No local Postgres or Redis; reads `DATABASE_URL` and `REDIS_URL` from `.env`.

```bash
docker compose down
docker compose -f docker-compose.local.yml down

# First time
docker compose -f docker-compose.remote.yml build
docker compose -f docker-compose.remote.yml run --rm api alembic upgrade head
docker compose -f docker-compose.remote.yml run --rm api python scripts/seed_dummy_data.py
docker compose -f docker-compose.remote.yml run --rm api python scripts/apply_queries_document.py

# Run all three
docker compose -f docker-compose.remote.yml up
```

API: http://localhost:8000/docs

**What this file does:**

| Setting | Behavior |
|---------|----------|
| No `postgres` / `redis` services | Uses Supabase + Upstash from `.env` |
| No `DATABASE_URL` / `REDIS_URL` overrides | `.env` values are respected |
| `./local/snapshots` volume on api + worker | Local snapshot storage works inside containers |
| Steampipe in worker image | No local Steampipe install needed on Mac |

Stop:

```bash
docker compose -f docker-compose.remote.yml down
```

View logs:

```bash
docker compose -f docker-compose.remote.yml logs -f worker
```

---

## Prerequisites (local scripts only)

- **Python 3.11+** (3.12 works). System Python 3.9 will fail on type syntax in models.
- **Steampipe** installed locally for the worker: [steampipe.io/docs/install](https://steampipe.io/docs/install)
- **AWS plugin:** `steampipe plugin install aws`
- **`.env`** in repo root with remote `DATABASE_URL` and `REDIS_URL`

---

## Step 1 — Configure `.env`

Copy from `env.example` and set remote URLs.

### Postgres (Supabase)

**Important for Docker:** Supabase **direct** host `db.<project>.supabase.co` is often **IPv6-only**. Docker Desktop usually has **no IPv6 route**, so you get:

`Network is unreachable` … `(2600:1f14:...)`

**Use the Session pooler URL from Supabase** (has IPv4), not the direct connection:

1. Supabase → **Project Settings** → **Database** → **Connection string**
2. Choose **Session pooler** (port **5432**) or **Transaction pooler** (port **6543**)
3. Copy the URI — it looks like:

```env
DATABASE_URL=
```

Note: pooler user is `postgres.<project-ref>`, not just `postgres`.

**Do not use** (IPv6-only, breaks in Docker):

```env
DATABASE_URL=postgresql://postgres:...@db.xxxx.supabase.co:5432/postgres
```

### Redis (Upstash example)

Upstash uses TLS (`rediss://`):

```env
REDIS_URL=rediss://default:YOUR_UPSTASH_TOKEN@YOUR_ENDPOINT.upstash.io:6379
```

**Common mistake — wrong format:**

```env
# BAD — nested assignment and extra quotes
REDIS_URL=REDIS_URL="rediss://..."
```

**Correct:**

```env
REDIS_URL=rediss://default:YOUR_TOKEN@your-endpoint.upstash.io:6379
```

### Snapshots (local, no S3 required for dev)

```env
USE_LOCAL_STORAGE=true
LOCAL_STORAGE_PATH=./local/snapshots
```

### AWS (worker — required for AWS queries)

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...   # optional; required for temporary credentials
```

Session tokens **expire**. Refresh them in `.env` when the worker reports credential errors.

### Steampipe (worker on macOS)

```env
STEAMPIPE_PATH=/usr/local/bin/steampipe
STEAMPIPE_CONFIG_DIR=/tmp/steampipe
STEAMPIPE_DATABASE_PORT=9194
STEAMPIPE_DATABASE_INSECURE=true
STEAMPIPE_CONNECTION_INIT_WAIT_SECONDS=45
```

---

## Step 2 — Python environment (one time)

From repo root:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Use `python3.11` or `python3.12` — not system `python3` if it is 3.9 or older.

---

## Step 3 — Initialize remote database (one time)

Migrations and seed run **against Supabase** (or whatever `DATABASE_URL` points to):

```bash
source venv/bin/activate
./scripts/init_db.sh
python scripts/seed_dummy_data.py
python scripts/apply_queries_document.py
```

| Script | What it does |
|--------|----------------|
| `init_db.sh` | `alembic upgrade head` — creates `public` tables + `compliance` schema |
| `seed_dummy_data.py` | Sample tenants, accounts, users, a few queries |
| `apply_queries_document.py` | Loads **49 queries** from `data/queries.json` |

Verify in Supabase **Table Editor**: `tenants`, `queries`, `execution_jobs` in schema `public`.

Re-running seed on the same DB may conflict on unique names — use a fresh Supabase project or skip seed if data already exists.

---

## Step 4 — Start the three processes

Open **three terminals**. In each:

```bash
cd /path/to/steampipe
source venv/bin/activate
```

| Terminal | Command | Purpose |
|----------|---------|---------|
| 1 | `./scripts/run_api.sh` | API → http://localhost:8000/docs |
| 2 | `./scripts/run_worker.sh` | Consumes Redis queue, runs Steampipe |
| 3 | `./scripts/run_scheduler.sh` | Cron schedules (optional) |

All processes load `.env` from the repo root via `src/config/settings.py`.

---

## Step 5 — Smoke test

### Health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/tenants
```

### Run one execution

1. Get IDs:

```bash
curl http://localhost:8000/api/v1/tenants
curl http://localhost:8000/api/v1/tenants/TENANT_ID/accounts
curl "http://localhost:8000/api/v1/queries?provider=aws&active=true"
```

2. Enqueue (account `provider` must match query `provider`, e.g. both `aws`):

```bash
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "YOUR_TENANT_ID",
    "account_id": "YOUR_ACCOUNT_ID",
    "query_id": "YOUR_QUERY_ID"
  }'
```

3. Watch **worker terminal** for processing logs.

4. Poll result:

```bash
curl http://localhost:8000/api/v1/executions/JOB_ID
curl http://localhost:8000/api/v1/executions/JOB_ID/result
curl http://localhost:8000/api/v1/executions/JOB_ID/result/data
```

Snapshot file (if `USE_LOCAL_STORAGE=true`) appears under:

```
./local/snapshots/acme-corp/aws/387957186076/2026/06/20/.../result.json
```

---

## Architecture with remote infra

```mermaid
flowchart LR
    subgraph Mac["Your machine"]
        API[run_api.sh]
        W[run_worker.sh]
        S[run_scheduler.sh]
        SN[local/snapshots]
        SP[Steampipe]
    end

    subgraph Remote["Remote (.env)"]
        PG[(Supabase Postgres)]
        RD[(Upstash Redis)]
    end

    AWS[AWS APIs]

    API --> PG
    API --> RD
    W --> PG
    W --> RD
    W --> SP
    SP --> AWS
    W --> SN
    S --> PG
    S --> RD
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Redis connection error | Malformed `REDIS_URL` | Single line, no nested `REDIS_URL=` or extra quotes |
| Postgres SSL / connection refused | Missing SSL or wrong host | Add `?sslmode=require`; use direct Supabase host (5432) |
| `Network is unreachable` to Supabase IPv6 from Docker | Direct `db.*.supabase.co` is **IPv6-only**; Docker has no IPv6 | Switch to **Session pooler** URL from Supabase dashboard (see Postgres section above) |
| `Network is unreachable` (other hosts) | Docker has no IPv6 route | Code sets `hostaddr` IPv4 when an A record exists; rebuild image, or use pooler URL |
| `GET /` returns 404 | No root route | Use http://localhost:8000/docs or `/health` |
| `TypeError: unsupported operand type(s) for \|` | Python 3.9 | Recreate venv with `python3.12` |
| Worker: AWS credentials not found | Empty or expired creds | Update `.env`; refresh session token if using STS |
| Jobs stay `queued` | Worker not running | Start `./scripts/run_worker.sh` |
| Jobs stay `running` forever | Worker crashed/restarted | Check worker logs; poll job status again |
| Still connecting to localhost DB | Docker compose running | `docker compose down`; use scripts, not compose |
| `could not translate host name` | Network / wrong URL | Check Supabase project is active; verify URI |

### Test Redis connectivity

```bash
source venv/bin/activate
python -c "
from src.services.queue import QueueService
q = QueueService()
print('Redis OK, queue depth:', q.length())
"
```

### Test Postgres connectivity

```bash
source venv/bin/activate
python -c "
from src.services.database import get_db_session_factory
s = get_db_session_factory()()
print('Postgres OK, tenants:', s.execute(__import__('sqlalchemy').text('select count(*) from tenants')).scalar())
s.close()
"
```

### Debug AWS

```bash
source venv/bin/activate
python scripts/check_aws_connectivity.py
```

---

## When to use local Docker DBs instead

Use **`docker-compose.local.yml`** or full **`docker compose up`** when:

- You want to reset the DB quickly (`docker compose down -v`)
- You are offline or avoiding cloud costs
- You are learning the project and do not have Supabase/Upstash yet

Use **this guide (remote DBs)** when:

- You already have Supabase + Upstash in `.env`
- You want persistent data across restarts
- You are closer to a staging/production-like setup

---

## Security notes

- **Never commit `.env`** — it contains database passwords and AWS keys.
- Add `.env` to `.gitignore` (already should be).
- Rotate credentials if `.env` was shared or committed by mistake.
- Supabase: restrict database access to your IP if possible (Database Settings → Network).

---

## Quick checklist

- [ ] `.env` has correct `DATABASE_URL` (Supabase direct, `sslmode=require`)
- [ ] `.env` has correct `REDIS_URL` (Upstash `rediss://`, no typos)
- [ ] `docker compose down` — no local Postgres/Redis running
- [ ] `python3.12 -m venv venv` + `pip install -r requirements.txt`
- [ ] `./scripts/init_db.sh` + seed + apply queries
- [ ] `./scripts/run_api.sh` + worker + scheduler **OR** `docker compose -f docker-compose.remote.yml up`
- [ ] `curl http://localhost:8000/health` → healthy
- [ ] One test `POST /api/v1/executions` → worker logs → `GET .../result/data`

---

## Related docs

| Doc | Topic |
|-----|-------|
| [STAGE1_FULL_GUIDE.md](STAGE1_FULL_GUIDE.md) | Full Stage 1 guide, all APIs |
| [LOCAL_DEVELOPMENT.md](../LOCAL_DEVELOPMENT.md) | Migrations, local dev workflow |
| [FRESH_DB_SETUP.md](../FRESH_DB_SETUP.md) | Reset with local Docker Postgres/Redis |
| [env.example](../env.example) | Template environment variables |
| [README.md](../README.md) | Project overview |
