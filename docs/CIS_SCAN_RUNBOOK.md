# CIS scan (multi-query) — run after apply_queries_document.py

## Snapshot format (schema v1.0)

Each `result.json` includes lineage metadata:

```json
{
  "metadata": {
    "execution_job_id": "...",
    "query_id": "...",
    "control_ref": "...",
    "framework_id": "cis_aws_v6",
    "row_count": 0,
    "schema_version": "1.0"
  },
  "columns": [...],
  "rows": [...]
}
```

## Query catalog

After changing `data/queries.json`:

```bash
python scripts/enrich_compliance_queries.py
python scripts/apply_queries_document.py
```

Scan runs **35 CIS v6 automated controls** (`cis_*` queries); legacy supplemental queries are excluded from scan.

## Full CIS AWS scan for one account

```bash
curl -X POST "http://localhost:8000/api/v1/executions/scan" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "YOUR_TENANT_UUID",
    "account_id": "YOUR_ACCOUNT_UUID",
    "framework_id": "cis_aws_v6",
    "category": "compliance"
  }'
```

Response includes `batch_id`, `total_jobs`, and `job_ids`. Poll progress:

```bash
curl "http://localhost:8000/api/v1/executions/batches/BATCH_ID"
```

List jobs in the scan:

```bash
curl "http://localhost:8000/api/v1/executions?batch_id=BATCH_ID&limit=100"
```

## Scale workers (recommended)

```bash
docker compose -f docker-compose.remote.yml up --scale worker=2
```

## Job completed events

Each successful job publishes to Redis list `steampipe:job_completed` with
`snapshot_path`, `control_ref`, `batch_id`, etc. (for compliance extract wiring).

## Bulk with explicit query IDs

`POST /api/v1/executions/bulk` now returns a `batch_id` and links all jobs to one batch.
