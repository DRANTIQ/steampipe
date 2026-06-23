# API Reference

Compliance API base URL: **http://localhost:8001**

Interactive docs: **http://localhost:8001/docs**

**Auth / tenant:** Send header on every request:

```
X-Tenant-Id: <tenant-uuid>
```

---

## Customer endpoints (build UI on these)

### Scan history

```
GET /v1/scan-runs?account_id={uuid}&framework_id=cis_aws_v6&limit=20
```

Response: list of `ScanRunResponse`

| Field | Description |
|-------|-------------|
| `batch_id` | Same as Stage 1 execution batch |
| `status` | `running` \| `completed` |
| `pass_count`, `fail_count` | Control counts |
| `score_pct` | Pass percentage (e.g. 77.14) |
| `finished_at` | Scan completion time |

### Scan summary

```
GET /v1/scan-runs/{batch_id}
```

### Control matrix (one scan)

```
GET /v1/scan-runs/{batch_id}/controls
```

Response: list of controls with `control_id`, `title`, `severity`, `status`, `evidence_count`, `control_result_id`

### Latest posture (all controls)

```
GET /v1/control-status/latest?account_id={uuid}&framework_id=cis_aws_v6
```

### Evidence drill-down

```
GET /v1/control-results/{result_id}/evidence
```

Returns `evidence_resources` with `resource_type`, `resource_id`, `payload_excerpt`

### Control catalog

```
GET /v1/controls?framework_id=cis_aws_v6
```

---

## Operations endpoints

### Backfill batch (snapshots already on disk)

```
POST /v1/scan-runs/{batch_id}/process
```

Reads `execution_jobs` + `execution_results` from Stage 1 DB, runs full pipeline for each job.

### Manual ingest (extract only)

```
POST /v1/snapshots/ingest
Content-Type: application/json

{
  "snapshot_path": "local/snapshots/.../result.json",
  "account_id": "uuid",
  "execution_job_id": "optional"
}
```

### Manual evaluate (one control)

```
POST /v1/evaluation-runs
Content-Type: application/json

{
  "account_id": "uuid",
  "s3_prefix": "local/snapshots/.../result.json",
  "framework_id": "cis_aws_v6",
  "control_ref": "security-hub-enabled"
}
```

Or with existing snapshot: `"snapshot_id": "uuid"`, `"control_ref": "..."`

### Simulate (no DB writes)

```
POST /v1/simulate
{ "snapshot_id": "uuid" }
```

---

## Example session

```powershell
$T = "5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47"
$B = "beef0081-5617-4ca4-bf6a-5480dd7aeab4"
$A = "e0e0075b-310d-4e37-9997-81626fe52580"

# Backfill
curl.exe -X POST "http://localhost:8001/v1/scan-runs/$B/process" -H "X-Tenant-Id: $T"

# Summary
curl.exe "http://localhost:8001/v1/scan-runs/$B" -H "X-Tenant-Id: $T"

# Matrix
curl.exe "http://localhost:8001/v1/scan-runs/$B/controls" -H "X-Tenant-Id: $T"

# History
curl.exe "http://localhost:8001/v1/scan-runs?account_id=$A" -H "X-Tenant-Id: $T"
```

---

## Health

```
GET /health
→ { "status": "ok" }
```

---

## Error codes

| Code | Meaning |
|------|---------|
| 400 | Missing `X-Tenant-Id`, bad body |
| 404 | Scan/batch/snapshot not found |
| 422 | Invalid UUID in header |
