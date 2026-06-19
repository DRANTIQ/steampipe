# User Input / Configuration

**Use this file as the canonical source for `.env`.** All infrastructure is **remote**: Postgres, Redis, and S3. When implementing from scratch (e.g. in Cursor), copy these values into `.env` and wire config to read them.

## Redis DB

Use in `.env` as `REDIS_URL`:

```
REDIS_URL=redis://default:lZStScEstEITjaITMJKhTzRFxNOqSOBE@shuttle.proxy.rlwy.net:47076
```

## Postgres DB

Use in `.env` as `DATABASE_URL`:

```
DATABASE_URL=postgresql://postgres:NekKloaoNNkTfkAdkjfLBthiadntSysX@shinkansen.proxy.rlwy.net:26194/railway
```

## Snapshots (S3)

Use in `.env`:

- **If local:** path `./local/snapshots`
- **S3:**
  - `arn:aws:s3:::steampipe-data-storage`
  - `S3_REGION=us-east-1`
  - `AWS_ACCESS_KEY_ID=...` (master account for Steampipe AWS / assume-role)
  - `AWS_SECRET_ACCESS_KEY=...`
  - `AWS_SESSION_TOKEN=...` (optional; for temporary credentials)

## Environment

| Variable | Value |
|----------|-------|
| `JWT_SECRET_KEY` | dev-secret |
| `API_AUTH_REQUIRED` | false |
| `SCHEDULER_ENABLED` | true |
| `MAX_CONCURRENT_EXECUTIONS` | 3 |

## Running locally

```bash
STEAMPIPE_PATH=/usr/local/bin/steampipe
STEAMPIPE_CONFIG_DIR=/tmp/steampipE
```
