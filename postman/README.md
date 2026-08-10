# Postman — Steampipe API

Import these files into Postman to exercise the Stage 1 API.

## Files

| File | Purpose |
|------|---------|
| `Steampipe-API.postman_collection.json` | All endpoints, shared scripts, smoke workflow |
| `environments/Steampipe-Local.postman_environment.json` | Local API (`./scripts/run_api.sh`) |
| `environments/Steampipe-Remote-Docker.postman_environment.json` | API in Docker (`docker compose -f docker-compose.remote.yml up`) |

Both environments default to `http://localhost:8000`. Change `baseUrl` if your API runs elsewhere.

## Import

1. Postman → **Import** → select all three JSON files (or import the `postman/` folder).
2. Top-right environment dropdown → select **Steampipe — Local** or **Steampipe — Remote (Docker)**.
3. Open the collection → **Variables** tab should be empty (runtime IDs live in the **environment**, not the collection).

## Variable scope (best practice)

| Scope | Variables | Who sets them |
|-------|-----------|---------------|
| **Environment** | `baseUrl`, `apiVersion`, `authToken`, `tenantId`, `accountId`, `queryId`, `jobId`, … | You (static) + test scripts (dynamic) |
| **Collection** | _(none — requests use environment only)_ | — |

Dynamic IDs are saved with `pm.environment.set()` after list/create calls so later requests reuse them.

## Quick smoke test

1. Seed data: `python scripts/seed_dummy_data.py`
2. Start API + worker
3. Select an environment
4. Run folder **Smoke Test Workflow** with Collection Runner

Steps 2–4 auto-fill `tenantId`, `accountId`, `queryId`. Step 5 enqueues a job (worker must be running).

## Headers & auth

Every API request sends these headers (visible in the **Headers** tab):

| Header | Value | When |
|--------|-------|------|
| `Accept` | `application/json` | All requests |
| `Content-Type` | `application/json` | POST / PUT / PATCH with a body |

**Authorization** is configured at **collection level** (not hidden in scripts):

1. Click the collection → **Authorization** tab
2. Type: **Bearer Token**
3. Token: `{{authToken}}` (from the active environment)

Each request uses **Auth → Inherit auth from parent** unless overridden (Health endpoints use **No Auth**).

| Mode | What to do |
|------|------------|
| **Dev (default)** | Leave `authToken` empty in the environment. Pre-request script skips Bearer when empty (`API_AUTH_REQUIRED=false`). |
| **Auth enabled** | Set `authToken` in the environment → Postman sends `Authorization: Bearer <token>`. |

> **Note:** Stage 1 does not validate JWT yet (`API_AUTH_REQUIRED=false` in `.env`). Headers are included for forward compatibility.

## Newman (CI)

```bash
npm install -g newman
newman run postman/Steampipe-API.postman_collection.json \
  -e postman/environments/Steampipe-Local.postman_environment.json \
  --folder "Smoke Test Workflow"
```

## OpenAPI

Interactive docs: `{{baseUrl}}/docs`
