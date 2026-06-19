# Steampipe in Docker: config and env (match reference setup)

This describes how we pass config and environment to Steampipe inside the worker container so it behaves the same as a reference “working” Steampipe-in-Docker setup (e.g. a zip or run script that passes everything in one place).

## Layout (same as reference)

- **One install dir** per worker: `STEAMPIPE_CONFIG_DIR/worker_install` (e.g. `/app/steampipe/worker_install`).
- **Config lives inside it**: `worker_install/config/` contains:
  - `default.spc` – database port.
  - `aws.spc` (or `<provider>.spc`) – one connection block for the current job.
  - `aws_credentials` – `[default]` credentials (direct or assumed-role).
  - `aws_config` – optional, for role_arn/source_profile when not using env-only.
- So: **STEAMPIPE_INSTALL_DIR** = `worker_install`, **STEAMPIPE_CONFIG_DIR** = `worker_install/config`. One tree, config and creds in the same place the service reads from.

## Environment we pass to the Steampipe service

Everything below is set in the process that starts `steampipe service start --foreground`, so the service and any plugin subprocess inherit the same env (like in a reference Docker run).

| Variable | Purpose |
|----------|---------|
| **STEAMPIPE_INSTALL_DIR** | Absolute path to worker_install (plugins, db, config parent). |
| **STEAMPIPE_CONFIG_DIR** | Absolute path to worker_install/config (where .spc and creds live). |
| **AWS_ACCESS_KEY_ID** | Set from assumed-role temp creds or master creds (so plugin sees them even if it doesn’t read the file). |
| **AWS_SECRET_ACCESS_KEY** | Same. |
| **AWS_SESSION_TOKEN** | Same (when using temp creds). |
| **AWS_SHARED_CREDENTIALS_FILE** | Absolute path to `worker_install/config/aws_credentials`. |
| **AWS_PROFILE** | `default`. |
| **AWS_CONFIG_FILE** | Absolute path to `worker_install/config/aws_config` when we use a config file. |
| **AWS_SDK_LOAD_CONFIG** | `1` when AWS_CONFIG_FILE is set (so SDK loads the config file). |
| **AWS_REGION** / **AWS_DEFAULT_REGION** | Account region or `us-east-1` (so plugin has a default region). |
| **HOME** | `/app` in Docker (so `~/.aws/credentials` = `/app/.aws/credentials`; we also write creds there). |
| **TMPDIR** | `worker_install/tmp` (same filesystem as install to avoid cross-device issues). |
| **SSL_CERT_FILE** / **SSL_CERT_DIR** | Worker install’s Steampipe root.crt (so the client trusts the service). |
| **HTTP_PROXY** / **HTTPS_PROXY** / **NO_PROXY** (and lowercase) | Forwarded from the container env so the plugin sees the same network/proxy as the host. |

## Credentials in two places (like reference)

1. **Config dir** – `worker_install/config/aws_credentials` and **AWS_SHARED_CREDENTIALS_FILE** pointing at it (absolute path).
2. **Default path** – We copy the same creds to **HOME/.aws/credentials** (e.g. `/app/.aws/credentials`) so any code that only checks the default path still works.

## Docker Compose

The worker service sets (so the Python process and thus Steampipe get them):

- **STEAMPIPE_CONFIG_DIR** = `/app/steampipe`
- **STEAMPIPE_PATH** = `/usr/local/bin/steampipe`
- **HOME** = `/app`
- **.env** for AWS master creds, DB, Redis, etc.

Proxy: if the host uses a proxy, set **HTTP_PROXY**, **HTTPS_PROXY**, **NO_PROXY** under `worker.environment` in docker-compose; the worker forwards them to the Steampipe service so the plugin uses the same proxy.

## Summary

Config and env are passed in one consistent way: one install dir, config and creds inside it, and the same env vars (AWS_*, STEAMPIPE_*, HOME, proxy, region) that a reference Steampipe Docker setup would use, so the container behaves the same as “that zip where everything worked.”
