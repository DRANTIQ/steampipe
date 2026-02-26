# 1. Create execution (save job_id from response)
curl -X 'POST' \
  'http://localhost:8000/api/v1/executions' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "tenant_id": "5c879ee7-08bb-4858-8000-f937e7a5582d",
  "account_id": "5c801cc9-3ac6-4777-be2c-6129a6acbddf",
  "query_id": "bd738e22-cf1c-4eb6-a8fb-3d57335603ab",
  "priority": 0,
  "triggered_by": "deva"
}'


a6cc104b-ac9c-46bf-a65d-e668caa52085
# 2. Poll job status until status is "success" or "failed" (worker must be running)
# Replace JOB_ID with the job_id from step 1. Do this before step 3 — result is only created when the worker finishes.
curl -s 'http://127.0.0.1:8000/api/v1/executions/JOB_ID' -H 'accept: application/json' | jq .

# 3. Get result metadata (row_count, duration, snapshot_path, error_message if failed)
# If you get 404 "Execution result not found", the response body will include the job status; wait for success/failed then retry.
curl -s 'http://127.0.0.1:8000/api/v1/executions/JOB_ID/result' -H 'accept: application/json' | jq .

# 4. Get the actual result data (Steampipe rows) — only after status is "success"
curl -s 'http://127.0.0.1:8000/api/v1/executions/JOB_ID/result/data' -H 'accept: application/json' | jq .

# --- Bulk: run multiple queries on one account (one job per query) ---
# Replace tenant_id, account_id, and query_ids (e.g. all 17 query IDs from GET /queries).
curl -X 'POST' 'http://localhost:8000/api/v1/executions/bulk' \
  -H 'accept: application/json' -H 'Content-Type: application/json' \
  -d '{"tenant_id": "TENANT_ID", "account_id": "ACCOUNT_ID", "query_ids": ["QUERY_ID_1", "QUERY_ID_2"]}'

# --- Run all queries for a provider on one account (batch): get query IDs by provider, then bulk ---
# 1) List all query IDs for provider (e.g. aws); then 2) bulk with those IDs (batch of 200 if > 200).
curl -s 'http://localhost:8000/api/v1/queries?provider=aws&limit=500' -H 'accept: application/json' | jq '.[].id'
# 2) Use those IDs in POST /executions/bulk (tenant_id, account_id, query_ids). For subset (e.g. 10 or 20), pass only those query_ids.

# --- Schedule: run one query on all AWS accounts for tenant (scheduler creates one job per account) ---
# Create schedule; run scheduler process (run_scheduler.sh) so jobs are enqueued at cron time.
curl -X 'POST' 'http://localhost:8000/api/v1/schedules' \
  -H 'accept: application/json' -H 'Content-Type: application/json' \
  -d '{"tenant_id": "TENANT_ID", "query_id": "QUERY_ID", "cron_expression": "0 */6 * * *", "timezone": "UTC", "enabled": true}'

# List schedules
curl -s 'http://localhost:8000/api/v1/schedules?tenant_id=TENANT_ID' -H 'accept: application/json' | jq .