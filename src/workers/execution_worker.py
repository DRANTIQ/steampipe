"""Execution worker: poll Redis, run Steampipe, persist snapshot, update DB. Only component that runs Steampipe."""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.config import get_settings

_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Keys we never log values for (sanitize for debug)
_DEBUG_SENSITIVE_KEYS = frozenset(
    {"secret", "aws_secret_access_key", "aws_session_token", "password", "token", "external_id"}
)

_macos_cert_hint_logged = False

from src.models import ExecutionBatch, ExecutionJob, ExecutionResult, CloudAccount, Query
from src.models.enums import ExecutionJobStatus, ExecutionResultStatus
from src.services.database import get_db_session_factory
from src.services.queue import QueueService
from src.services.snapshot import SnapshotService
from src.services.secrets import SecretsService

# Steampipe connection block uses short plugin name (e.g. "aws"), not hub name ("steampipe-aws" / "turbot/aws").
_PLUGIN_NAME_FOR_CONNECTION = {"steampipe-aws": "aws", "turbot/aws": "aws"}


def _plugin_for_connection(plugin: str) -> str:
    """Return the plugin name to use in the .spc connection block (short name Steampipe expects)."""
    return _PLUGIN_NAME_FOR_CONNECTION.get(plugin.strip().lower(), plugin)


# AWS plugin only accepts these connection options; extra keys (e.g. additionalProp1 from API) can break init.
_AWS_CONNECTION_OPTIONS = frozenset({"profile", "regions", "ignore_errors", "max_error_concurrency", "max_concurrent_connections"})


def _conn_config_to_hcl(conn_config: dict, plugin: str) -> str:
    """Build HCL connection block body from conn_config. For AWS, role_arn/external_id are in a profile (not here)."""
    plugin_name = _plugin_for_connection(plugin)
    lines = [f'  plugin = "{plugin_name}"']
    # For AWS, only pass through known options so we don't write additionalProp1 etc. that break the plugin.
    allowed = _AWS_CONNECTION_OPTIONS if plugin_name == "aws" else None
    for key, value in conn_config.items():
        if key in ("connection_name", "plugin", "role_arn", "external_id"):
            continue
        if allowed is not None and key not in allowed:
            continue
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"  {key} = {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"  {key} = {value}")
        elif isinstance(value, list):
            if all(isinstance(v, str) for v in value):
                items = ", ".join(f'"{v}"' for v in value)
                lines.append(f"  {key} = [{items}]")
            else:
                items = ", ".join(str(v) for v in value)
                lines.append(f"  {key} = [{items}]")
        else:
            escaped = str(value).replace('"', '\\"').replace("\n", " ")
            lines.append(f'  {key} = "{escaped}"')
    return "\n".join(lines)


def _sanitize_for_log(obj: dict) -> dict:
    """Return a copy with sensitive values replaced by '***' for debug logging."""
    out = {}
    for k, v in obj.items():
        key_lower = k.lower() if isinstance(k, str) else ""
        out[k] = "***" if key_lower in _DEBUG_SENSITIVE_KEYS or "secret" in key_lower or "token" in key_lower else v
    return out


def _write_aws_credentials_file(config_dir: Path) -> bool:
    """Write [default] master credentials to config_dir/aws_credentials from settings. Returns True if written."""
    s = get_settings()
    if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY):
        logger.debug("AWS credentials not in settings; skipping aws_credentials file")
        return False
    lines = ["[default]", f"aws_access_key_id = {s.AWS_ACCESS_KEY_ID}", f"aws_secret_access_key = {s.AWS_SECRET_ACCESS_KEY}"]
    if s.AWS_SESSION_TOKEN:
        lines.append(f"aws_session_token = {s.AWS_SESSION_TOKEN}")
    creds_file = config_dir / "aws_credentials"
    creds_file.write_text("\n".join(lines) + "\n")
    logger.debug("Wrote aws_credentials to %s", creds_file)
    return True


def _assume_role_and_get_credentials(
    role_arn: str,
    external_id: str | None,
    region: str | None,
    role_session_name: str = "steampipe-session",
) -> dict[str, str] | None:
    """
    Assume the given IAM role using master credentials from settings (same as reference run.sh).
    Returns dict with AccessKeyId, SecretAccessKey, SessionToken for the child account, or None on failure.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        logger.warning("boto3 not available; cannot assume role")
        return None
    s = get_settings()
    if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY):
        return None
    kwargs = {
        "aws_access_key_id": s.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": s.AWS_SECRET_ACCESS_KEY,
        "region_name": region or s.S3_REGION,
    }
    if s.AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = s.AWS_SESSION_TOKEN
    sts = boto3.client("sts", **kwargs)
    assume_kwargs = {"RoleArn": role_arn, "RoleSessionName": role_session_name}
    if external_id is not None and str(external_id).strip():
        assume_kwargs["ExternalId"] = str(external_id).strip()
    try:
        resp = sts.assume_role(**assume_kwargs)
        creds = resp["Credentials"]
        return {
            "AccessKeyId": creds["AccessKeyId"],
            "SecretAccessKey": creds["SecretAccessKey"],
            "SessionToken": creds["SessionToken"],
        }
    except ClientError as e:
        logger.warning("STS AssumeRole failed: %s", e.response.get("Error", {}).get("Message", e))
        return None


def _write_assumed_credentials_file(config_dir: Path, assumed: dict[str, str]) -> Path:
    """Write [default] with assumed-role temporary credentials. Returns path to the credentials file."""
    lines = [
        "[default]",
        f"aws_access_key_id = {assumed['AccessKeyId']}",
        f"aws_secret_access_key = {assumed['SecretAccessKey']}",
        f"aws_session_token = {assumed['SessionToken']}",
    ]
    creds_file = config_dir / "aws_credentials"
    creds_file.write_text("\n".join(lines) + "\n")
    logger.debug("Wrote assumed-role credentials to %s", creds_file)
    return creds_file


def _log_aws_creds_and_verify_get_caller_identity(
    assumed: dict[str, str],
    job_id: str,
    region: str | None = None,
) -> None:
    """
    Call STS GetCallerIdentity with the given creds and log the result.
    If DEBUG_AWS_CREDENTIALS=1, also log the full credentials (insecure; for debugging only).
    """
    log_creds = os.environ.get("DEBUG_AWS_CREDENTIALS", "").strip().lower() in ("1", "true", "yes")
    if log_creds:
        logger.warning(
            "[DEBUG_AWS_CREDENTIALS] Job %s credentials being passed to Steampipe: AccessKeyId=%s SecretAccessKey=%s SessionToken=%s",
            job_id,
            assumed.get("AccessKeyId", ""),
            assumed.get("SecretAccessKey", ""),
            assumed.get("SessionToken", ""),
        )
    try:
        import boto3
        sts = boto3.client(
            "sts",
            aws_access_key_id=assumed["AccessKeyId"],
            aws_secret_access_key=assumed["SecretAccessKey"],
            aws_session_token=assumed["SessionToken"],
            region_name=region or get_settings().S3_REGION,
        )
        identity = sts.get_caller_identity()
        logger.info(
            "Job %s: STS GetCallerIdentity OK Account=%s Arn=%s UserId=%s",
            job_id,
            identity.get("Account"),
            identity.get("Arn"),
            identity.get("UserId"),
        )
    except Exception as e:
        logger.warning(
            "Job %s: STS GetCallerIdentity FAILED (same creds we pass to Steampipe): %s",
            job_id,
            e,
        )


def _setup_aws_assume_role_profile(config_dir: Path, conn_config: dict) -> tuple[dict[str, str], str]:
    """
    Create AWS config and credentials files. Profile uses source_profile=default (creds from file),
    so the Steampipe service/plugin does not need AWS_* env vars.
    Returns (env_overrides for subprocess, profile_name to use in connection).
    """
    role_arn = conn_config.get("role_arn")
    if not role_arn or not isinstance(role_arn, str):
        return {}, ""
    _write_aws_credentials_file(config_dir)
    external_id = conn_config.get("external_id")
    profile_name = "steampipe_assume"
    config_path = config_dir / "aws_config"
    lines = [f"[profile {profile_name}]", f"role_arn = {role_arn}", "source_profile = default"]
    if external_id is not None and str(external_id).strip():
        lines.append(f'external_id = {str(external_id).strip()}')
    config_path.write_text("\n".join(lines) + "\n")
    creds_path = config_dir / "aws_credentials"
    env = {"AWS_CONFIG_FILE": str(config_path), "AWS_SHARED_CREDENTIALS_FILE": str(creds_path), "AWS_PROFILE": profile_name}
    logger.debug("Assume-role profile: profile_name=%s, role_arn=%s, config=%s", profile_name, role_arn, config_path)
    return env, profile_name


def _find_steampipe_root_crt(install_dir: str) -> str | None:
    """Find root.crt under install_dir/db (e.g. ~/.steampipe/db/14.x.x/data/root.crt)."""
    db_dir = Path(install_dir) / "db"
    if not db_dir.exists():
        return None
    for path in db_dir.iterdir():
        if path.is_dir():
            candidate = path / "data" / "root.crt"
            if candidate.exists():
                return str(candidate)
    return None


def _ensure_worker_install_has_cert(worker_install: Path, steampipe_path: str, port: int) -> str | None:
    """
    Ensure worker_install has a DB and root.crt so the client can trust the service.
    If missing, start the service in foreground, poll for root.crt to appear, then stop it.
    Returns path to root.crt or None.
    """
    root_crt = _find_steampipe_root_crt(str(worker_install))
    if root_crt:
        return root_crt
    env = os.environ.copy()
    env["STEAMPIPE_INSTALL_DIR"] = str(worker_install)
    env["STEAMPIPE_CONFIG_DIR"] = str(worker_install / "config")
    tmp_dir = worker_install / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(tmp_dir)
    proc = None
    try:
        proc = subprocess.Popen(
            [steampipe_path, "service", "start", "--foreground"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=env,
        )
        for _ in range(30):  # 30 * 2s = 60s max
            time.sleep(2)
            root_crt = _find_steampipe_root_crt(str(worker_install))
            if root_crt:
                logger.info("Bootstrap: Steampipe cert ready at %s", root_crt)
                break
            if proc.poll() is not None:
                break
    except FileNotFoundError:
        pass
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            subprocess.run(
                [steampipe_path, "service", "stop"],
                capture_output=True,
                text=True,
                timeout=15,
                env={**os.environ, "STEAMPIPE_INSTALL_DIR": str(worker_install)},
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return _find_steampipe_root_crt(str(worker_install))


def _add_cert_to_macos_keychain(root_crt: str) -> bool:
    """On macOS, Go ignores SSL_CERT_FILE and uses the system keychain. Add worker cert to login keychain (no sudo)."""
    if sys.platform != "darwin":
        return False
    keychain = os.path.expanduser("~/Library/Keychains/login.keychain-db")
    if not Path(keychain).exists():
        keychain = os.path.expanduser("~/Library/Keychains/login.keychain")
    if not Path(keychain).exists():
        return False
    try:
        r = subprocess.run(
            ["security", "add-certificates", "-k", keychain, root_crt],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False




def _run_steampipe_query(
    query_text: str,
    plugin: str,
    output_format: str,
    config_dir: Path,
    steampipe_path: str,
    *,
    connection_name: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[dict | list, int, float, str | None]:
    """Run steampipe query; return (parsed_output, row_count, duration_seconds, error_message)."""
    start = time.perf_counter()
    cmd = [
        steampipe_path,
        "query",
        f"--output={output_format}",
    ]
    if connection_name:
        cmd.extend(["--search-path", connection_name])
    cmd.append(query_text)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    settings = get_settings()
    port = getattr(settings, "STEAMPIPE_DATABASE_PORT", 9194)
    worker_install = Path(settings.STEAMPIPE_CONFIG_DIR) / "worker_install"
    worker_install.mkdir(parents=True, exist_ok=True)
    saved_default_spc: str | None = None
    service_proc: subprocess.Popen | None = None  # foreground service, so we can terminate in finally
    service_stderr_path: str | None = None  # capture service stderr to diagnose connection errors
    service_stderr_file = None  # keep open until process exits so child can write

    logger.debug(
        "Steampipe query: plugin=%s, connection_name=%s, port=%s, worker_install=%s, config_dir=%s, extra_env_keys=%s",
        plugin,
        connection_name,
        port,
        worker_install,
        config_dir,
        list(extra_env.keys()) if extra_env else None,
    )
    logger.debug("Query (first 200 chars): %s", (query_text[:200] + "..." if len(query_text) > 200 else query_text))

    # Branch by platform: Docker runs Linux (else branch). macOS branch is for local dev on a Mac only.
    # On macOS, Go ignores SSL_CERT_FILE and uses the keychain; use ~/.steampipe so the cert is trusted.
    if sys.platform == "darwin":
        effective_install = Path.home() / ".steampipe"
        default_spc = effective_install / "config" / "default.spc"
        default_spc.parent.mkdir(parents=True, exist_ok=True)
        if default_spc.exists():
            saved_default_spc = default_spc.read_text()
        default_spc.write_text(f'options "database" {{\n  port = {port}\n}}\n')
        env["STEAMPIPE_INSTALL_DIR"] = str(effective_install)
        # Stop any existing service so the next query starts a fresh service that loads this job's config.
        try:
            subprocess.run(
                [steampipe_path, "service", "stop"],
                capture_output=True,
                timeout=15,
                env={**env, "STEAMPIPE_INSTALL_DIR": str(effective_install)},
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    else:
        effective_install = worker_install
        (worker_install / "config").mkdir(parents=True, exist_ok=True)
        (worker_install / "config" / "default.spc").write_text(f'options "database" {{\n  port = {port}\n}}\n')
        # Copy job's connection config and AWS credential files into install dir so the service loads them
        job_config = Path(config_dir) / "config"
        spc_copied = [f.name for f in job_config.glob("*.spc")]
        for f in job_config.glob("*.spc"):
            (worker_install / "config" / f.name).write_text(f.read_text())
        for name in ("aws_credentials", "aws_config"):
            src = config_dir / name
            if src.exists():
                (worker_install / "config" / name).write_text(src.read_text())
        creds_copied = [n for n in ("aws_credentials", "aws_config") if (config_dir / n).exists()]
        logger.info(
            "Steampipe config: .spc=%s creds_copied=%s worker_install=%s env_has_AWS_ACCESS_KEY_ID=%s",
            spc_copied,
            creds_copied,
            worker_install,
            "AWS_ACCESS_KEY_ID" in env,
        )
        wi_config = worker_install / "config"
        # Same layout as reference Steampipe-in-Docker: one install dir, config and creds inside it.
        env["STEAMPIPE_INSTALL_DIR"] = str(worker_install)
        env["STEAMPIPE_CONFIG_DIR"] = str(wi_config)
        if (wi_config / "aws_credentials").exists():
            env["AWS_SHARED_CREDENTIALS_FILE"] = str(wi_config / "aws_credentials")
            # Plugin may run as subprocess; many AWS SDKs also check ~/.aws/credentials. Set default path (e.g. HOME=/app in Docker).
            home = env.get("HOME", "/app")
            default_aws = Path(home) / ".aws"
            default_aws.mkdir(parents=True, exist_ok=True)
            default_creds = default_aws / "credentials"
            default_creds.write_text((wi_config / "aws_credentials").read_text())
            logger.info("Also wrote credentials to default path %s (for plugin subprocess)", default_creds)
        if (wi_config / "aws_config").exists():
            env["AWS_CONFIG_FILE"] = str(wi_config / "aws_config")
            env["AWS_SDK_LOAD_CONFIG"] = "1"
        # Default region so plugin/SDK have one (connection .spc can override per-connection).
        if "AWS_REGION" not in env and "AWS_DEFAULT_REGION" not in env:
            env["AWS_REGION"] = settings.S3_REGION
            env["AWS_DEFAULT_REGION"] = settings.S3_REGION
        # Inject AWS creds into env so the Steampipe service/plugin sees them (same as reference run.sh).
        if "AWS_ACCESS_KEY_ID" not in env and settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            env["AWS_ACCESS_KEY_ID"] = settings.AWS_ACCESS_KEY_ID
            env["AWS_SECRET_ACCESS_KEY"] = settings.AWS_SECRET_ACCESS_KEY
            if settings.AWS_SESSION_TOKEN:
                env["AWS_SESSION_TOKEN"] = settings.AWS_SESSION_TOKEN
            logger.debug("Set master AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in service env")
        elif "AWS_ACCESS_KEY_ID" in env:
            logger.debug("Using AWS creds from extra_env (e.g. assumed-role) in service env")
        else:
            logger.debug("No AWS creds in env; service will rely on credential files only")
        # No retries: get real error fast instead of 9 SDK retries (AWS_MAX_ATTEMPTS=1).
        env["AWS_MAX_ATTEMPTS"] = "1"
        # Forward proxy env so Steampipe/plugin see same network as container (like reference Docker setup).
        for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"):
            if proxy_var in os.environ and proxy_var not in env:
                env[proxy_var] = os.environ[proxy_var]
        logger.debug(
            "Env for service: STEAMPIPE_INSTALL_DIR=%s, STEAMPIPE_CONFIG_DIR=%s, AWS_SHARED_CREDENTIALS_FILE=%s, AWS_PROFILE=%s, AWS_REGION=%s",
            env.get("STEAMPIPE_INSTALL_DIR"),
            env.get("STEAMPIPE_CONFIG_DIR"),
            env.get("AWS_SHARED_CREDENTIALS_FILE"),
            env.get("AWS_PROFILE"),
            env.get("AWS_REGION"),
        )
        # Use same filesystem as install dir for temp files (avoids "invalid cross-device link" in Docker)
        tmp_dir = worker_install / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        env["TMPDIR"] = str(tmp_dir)
        root_crt = _find_steampipe_root_crt(str(worker_install)) or _ensure_worker_install_has_cert(
            worker_install, steampipe_path, port
        )
        # Query client needs SSL_CERT_FILE to trust the local Steampipe service. Do NOT pass it to the
        # service process: the AWS plugin would then use it for outbound HTTPS to AWS and fail with
        # "x509: certificate signed by unknown authority". Service/plugin must use system CA bundle for AWS.
        env_service = env.copy()
        if root_crt:
            env["SSL_CERT_FILE"] = root_crt
            env["SSL_CERT_DIR"] = str(Path(root_crt).parent)
            env_service.pop("SSL_CERT_FILE", None)
            env_service.pop("SSL_CERT_DIR", None)
        # Stop any existing service
        logger.debug("Stopping any existing Steampipe service (install=%s)", worker_install)
        try:
            stop_out = subprocess.run(
                [steampipe_path, "service", "stop"],
                capture_output=True,
                text=True,
                timeout=15,
                env={**env_service, "STEAMPIPE_INSTALL_DIR": str(worker_install)},
            )
            if stop_out.returncode != 0 and (stop_out.stderr or stop_out.stdout):
                logger.debug("Service stop output: stderr=%s stdout=%s", stop_out.stderr, stop_out.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("Service stop exception: %s", e)
        # Start the service in foreground so it inherits our env (background daemon may not).
        logger.info("Starting Steampipe service in foreground (port=%s) so env is inherited", port)
        service_proc = None
        try:
            stderr_file = worker_install / "tmp" / "service_stderr.txt"
            stderr_file.parent.mkdir(parents=True, exist_ok=True)
            service_stderr_path = str(stderr_file)
            service_stderr_file = open(service_stderr_path, "w")  # noqa: SIM115
            service_proc = subprocess.Popen(
                [steampipe_path, "service", "start", "--foreground"],
                stdout=subprocess.DEVNULL,
                stderr=service_stderr_file,
                env=env_service,
                text=True,
            )
        except FileNotFoundError:
            logger.warning("Steampipe binary not found, falling back to service start (background)")
            service_proc = None
            try:
                subprocess.run(
                    [steampipe_path, "service", "start"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env_service,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        # Wait for service to be listening
        for _ in range(15):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect(("127.0.0.1", port))
                s.close()
                break
            except OSError:
                time.sleep(2)
        else:
            if service_proc and service_proc.poll() is None:
                service_proc.terminate()
                try:
                    service_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    service_proc.kill()
            logger.debug("Steampipe service did not accept TCP connection on port %s within timeout", port)
            return {}, 0, time.perf_counter() - start, "Steampipe service did not start in time"

        # Give the plugin time to initialize the connection (schema creation, credentials, GetCallerIdentity).
        # AWS plugin can retry many times; 10s is often too short. Configurable via STEAMPIPE_CONNECTION_INIT_WAIT_SECONDS.
        wait_sec = getattr(settings, "STEAMPIPE_CONNECTION_INIT_WAIT_SECONDS", 45)
        logger.info("Service listening; waiting %ss for connection init then running query", wait_sec)
        time.sleep(wait_sec)
        # Flush and log service stderr so we see plugin init output / errors before running the query
        if service_stderr_path:
            try:
                service_stderr_file.flush()
                with open(service_stderr_path, "r") as f:
                    init_err = f.read().strip()
                if init_err:
                    logger.info("Steampipe service stderr after init wait: %s", init_err[-3000:] if len(init_err) > 3000 else init_err)
            except Exception as e:
                logger.debug("Could not read service stderr after wait: %s", e)
        logger.debug("Running steampipe query: cwd=%s cmd_prefix=%s", config_dir, cmd[:4])

    if "STEAMPIPE_CONFIG_DIR" not in env:
        env["STEAMPIPE_CONFIG_DIR"] = str(Path(config_dir) / "config")
    insecure = getattr(settings, "STEAMPIPE_DATABASE_INSECURE", False)
    if insecure:
        env["PGSSLMODE"] = "disable"
        env["PGSQL_SSLMODE"] = "disable"
        env["STEAMPIPE_DATABASE_SSLMODE"] = "disable"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(config_dir),
            env=env,
        )
        duration = time.perf_counter() - start
        if result.returncode != 0:
            err = (result.stderr or "").strip()
            out = (result.stdout or "").strip()
            combined = err or out or "Unknown error"
            if err and out:
                combined = f"{err}\n--- stdout ---\n{out}"
            # Log full error (no truncation) so we see the real failure.
            logger.error(
                "Steampipe query failed: returncode=%s connection_name=%s full_error=%s",
                result.returncode,
                connection_name,
                combined,
            )
            # Also log service stderr when available (plugin often writes the actual error there).
            if service_stderr_path:
                try:
                    p = Path(service_stderr_path)
                    if p.exists():
                        service_err = p.read_text().strip()
                        if service_err:
                            logger.error("Steampipe service stderr: %s", service_err)
                            combined = f"{combined}\n\n--- service stderr ---\n{service_err}"
                except Exception:
                    pass
            err_lower = combined.lower()
            if "request send failed" in err_lower or ("getcalleridentity" in err_lower and "statuscode: 0" in err_lower):
                hint = (
                    "Hint: The AWS plugin could not reach the AWS API (network error). "
                    "Ensure the worker/container has outbound HTTPS (443) to *.amazonaws.com, DNS resolves, "
                    "and if behind a proxy set HTTP_PROXY/HTTPS_PROXY for the Steampipe process."
                )
            elif "all connections in search path are in error" in err_lower:
                hint = (
                    "Hint: The connection failed to initialize. "
                    "Check credentials (AWS profile/role_arn), region, and that the plugin can reach the API."
                )
            else:
                hint = ""
            if hint:
                combined = f"{combined}\n\n{hint}"
            return {}, 0, duration, combined
        data = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(data, list):
            row_count = len(data)
        elif isinstance(data, dict):
            row_count = len(data.get("rows", [])) if "rows" in data else 1
        else:
            row_count = 0
        return data, row_count, duration, None
    except subprocess.TimeoutExpired:
        duration = time.perf_counter() - start
        return {}, 0, duration, "Timeout"
    except json.JSONDecodeError as e:
        duration = time.perf_counter() - start
        return {}, 0, duration, str(e)
    finally:
        if sys.platform == "darwin" and saved_default_spc is not None:
            default_spc_path = Path.home() / ".steampipe" / "config" / "default.spc"
            try:
                default_spc_path.write_text(saved_default_spc)
            except OSError:
                pass
        elif sys.platform != "darwin":
            if service_proc is not None and service_proc.poll() is None:
                try:
                    service_proc.terminate()
                    service_proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    service_proc.kill()
                except Exception:
                    pass
            try:
                if service_stderr_file is not None:
                    service_stderr_file.close()
            except Exception:
                pass
            try:
                subprocess.run(
                    [steampipe_path, "service", "stop"],
                    capture_output=True,
                    timeout=15,
                    env=env,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass


def _fail_job_connection(session: Session, job: ExecutionJob, job_id: str, message: str) -> None:
    """Mark job failed and create a failed result with the given message; commit."""
    job.status = ExecutionJobStatus.failed.value
    job.finished_at = datetime.now(timezone.utc)
    session.add(
        ExecutionResult(
            execution_job_id=job_id,
            status=ExecutionResultStatus.failed.value,
            error_message=message,
        )
    )
    if job.batch_id:
        _update_batch_on_job_finish(session, job.batch_id, False)
    session.commit()
    logger.warning("Job %s failed (credentials/setup): %s", job_id, message)


def _update_batch_on_job_finish(session: Session, batch_id: str, success: bool) -> None:
    """Increment batch completed_jobs or failed_jobs; if total reached, set status and finished_at."""
    stmt = (
        update(ExecutionBatch)
        .where(ExecutionBatch.id == batch_id)
        .values(
            completed_jobs=ExecutionBatch.completed_jobs + (1 if success else 0),
            failed_jobs=ExecutionBatch.failed_jobs + (0 if success else 1),
        )
    )
    result = session.execute(stmt)
    if result.rowcount == 0:
        return
    session.flush()
    batch = session.query(ExecutionBatch).filter(ExecutionBatch.id == batch_id).first()
    if not batch:
        return
    if batch.completed_jobs + batch.failed_jobs >= batch.total_jobs:
        if batch.failed_jobs == 0:
            batch.status = "completed"
        elif batch.completed_jobs == 0:
            batch.status = "failed"
        else:
            batch.status = "partial"
        batch.finished_at = datetime.now(timezone.utc)


def process_job(session: Session, job_id: str, payload: dict) -> None:
    """Process a single execution job: run Steampipe, persist snapshot, create result."""
    settings = get_settings()
    # Atomic claim: only proceed if job is still queued/retrying
    stmt = (
        update(ExecutionJob)
        .where(ExecutionJob.id == job_id)
        .where(ExecutionJob.status.in_([ExecutionJobStatus.queued.value, ExecutionJobStatus.retrying.value]))
        .values(
            status=ExecutionJobStatus.running.value,
            started_at=datetime.now(timezone.utc),
        )
    )
    result = session.execute(stmt)
    session.commit()
    if result.rowcount == 0:
        logger.info("Job %s already claimed or not queued, skipping", job_id)
        return
    job = session.query(ExecutionJob).filter(ExecutionJob.id == job_id).first()
    if not job:
        logger.warning("Job %s not found after claim, skipping", job_id)
        return
    logger.info("Processing job %s (tenant=%s, query=%s)", job_id, job.tenant_id, job.query_id)

    account = session.query(CloudAccount).filter(CloudAccount.id == job.account_id).first()
    query = session.query(Query).filter(Query.id == job.query_id).first()
    if not account or not query:
        logger.warning("Job %s: account or query not found, marking failed", job_id)
        job.status = ExecutionJobStatus.failed.value
        job.finished_at = job.started_at or datetime.now(timezone.utc)
        session.add(ExecutionResult(execution_job_id=job_id, status=ExecutionResultStatus.failed.value, error_message="Account or query not found"))
        if job.batch_id:
            _update_batch_on_job_finish(session, job.batch_id, False)
        session.commit()
        return

    snapshot_service = SnapshotService()
    secrets_service = SecretsService()
    config_dir = Path(settings.STEAMPIPE_CONFIG_DIR) / f"run_{job_id}"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_subdir = config_dir / "config"
    config_subdir.mkdir(parents=True, exist_ok=True)
    # Use a different port so worker doesn't conflict with default Steampipe on 9193
    port = getattr(settings, "STEAMPIPE_DATABASE_PORT", 9194)
    (config_subdir / "default.spc").write_text(f'options "database" {{\n  port = {port}\n}}\n')
    try:
        conn_config = secrets_service.get_connection_config(
            account.id, account.provider, account.secret_arn, account.extra_metadata
        )
        logger.debug(
            "Job %s: conn_config (sanitized)=%s, account.provider=%s, account.region=%s, secret_arn=%s",
            job_id,
            _sanitize_for_log(conn_config),
            account.provider,
            account.region,
            "(set)" if account.secret_arn else None,
        )
        extra_env: dict[str, str] = {}
        # AWS: match reference "run.sh" flow — assume role in our process, pass temp creds to Steampipe (plugin sees child creds only).
        if account.provider == "aws":
            if conn_config.get("role_arn"):
                role_arn = conn_config["role_arn"]
                external_id = conn_config.get("external_id")
                s = get_settings()
                if not (s.AWS_ACCESS_KEY_ID and s.AWS_SECRET_ACCESS_KEY):
                    _fail_job_connection(
                        session,
                        job,
                        job_id,
                        "Assume-role is configured but master credentials are missing. "
                        "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the worker environment (e.g. .env or docker-compose).",
                    )
                    return
                logger.info("Job %s: assuming role role_arn=%s", job_id, role_arn)
                assumed = _assume_role_and_get_credentials(
                    role_arn, external_id, account.region, role_session_name=f"steampipe-{job_id[:8]}"
                )
                if not assumed:
                    _fail_job_connection(
                        session,
                        job,
                        job_id,
                        "Failed to assume role (check role_arn, external_id, and that master credentials can call sts:AssumeRole).",
                    )
                    return
                logger.info("Job %s: AssumeRole succeeded, passing temp creds to Steampipe", job_id)
                _log_aws_creds_and_verify_get_caller_identity(assumed, job_id, region=account.region)
                creds_path = _write_assumed_credentials_file(config_dir, assumed)
                region = account.region or "us-east-1"
                extra_env = {
                    "AWS_ACCESS_KEY_ID": assumed["AccessKeyId"],
                    "AWS_SECRET_ACCESS_KEY": assumed["SecretAccessKey"],
                    "AWS_SESSION_TOKEN": assumed["SessionToken"],
                    "AWS_SHARED_CREDENTIALS_FILE": str(creds_path),
                    "AWS_PROFILE": "default",
                    "AWS_REGION": region,
                    "AWS_DEFAULT_REGION": region,
                }
                conn_config["profile"] = "default"
                if "regions" not in conn_config:
                    conn_config["regions"] = [account.region] if account.region else ["us-east-1"]
                logger.debug("Job %s: assumed role, passing temp creds to Steampipe (profile=default)", job_id)
            else:
                logger.info("Job %s: using direct AWS credentials (no assume-role)", job_id)
                if _write_aws_credentials_file(config_dir):
                    creds_path = config_dir / "aws_credentials"
                    region = account.region or "us-east-1"
                    extra_env = {
                        "AWS_SHARED_CREDENTIALS_FILE": str(creds_path),
                        "AWS_PROFILE": "default",
                        "AWS_REGION": region,
                        "AWS_DEFAULT_REGION": region,
                    }
                    conn_config["profile"] = "default"
                    if "regions" not in conn_config:
                        conn_config["regions"] = [account.region] if account.region else ["us-east-1"]
                    s = get_settings()
                    direct_creds = {
                        "AccessKeyId": s.AWS_ACCESS_KEY_ID,
                        "SecretAccessKey": s.AWS_SECRET_ACCESS_KEY,
                        "SessionToken": s.AWS_SESSION_TOKEN or "",
                    }
                    _log_aws_creds_and_verify_get_caller_identity(direct_creds, job_id, region=account.region)
                else:
                    _fail_job_connection(
                        session,
                        job,
                        job_id,
                        "AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in the worker environment.",
                    )
                    return
        # Write .spc (role_arn/external_id omitted here; they're in the AWS profile)
        spc = config_subdir / f"{account.provider}.spc"
        raw_name = conn_config.get("connection_name", f"{account.provider}_{account.id}")
        connection_name = raw_name.replace("-", "_").replace(" ", "_")
        plugin_for_spc = _plugin_for_connection(query.plugin)
        body = _conn_config_to_hcl(conn_config, query.plugin)
        spc_content = f'connection "{connection_name}" {{\n{body}\n}}\n'
        spc.write_text(spc_content)
        logger.info(
            "Job %s: wrote connection %s plugin=%s regions=%s (spc excerpt: %s)",
            job_id,
            connection_name,
            plugin_for_spc,
            conn_config.get("regions"),
            body[:150] + "..." if len(body) > 150 else body,
        )
        if account.provider == "aws" and not (config_dir / "aws_credentials").exists():
            logger.warning("Job %s: AWS master credentials not in settings; connection will likely fail", job_id)
        output, row_count, duration_seconds, error_message = _run_steampipe_query(
            query.query_text,
            query.plugin,
            query.output_format,
            config_dir,
            settings.STEAMPIPE_PATH,
            connection_name=connection_name,
            extra_env=extra_env or None,
        )
        if error_message:
            result_status = ExecutionResultStatus.failed.value
            snapshot_path = None
        else:
            result_status = ExecutionResultStatus.success.value
            snapshot_path = snapshot_service.persist_snapshot(
                tenant_id=job.tenant_id,
                execution_id=job_id,
                query_id=job.query_id,
                account_id=job.account_id,
                provider=account.provider,
                account_identifier=account.account_id,
                region=account.region,
                data=output if isinstance(output, dict) else {"rows": output},
            )
        job.finished_at = datetime.now(timezone.utc)
        success = not error_message
        if success:
            job.status = ExecutionJobStatus.success.value
            result = ExecutionResult(
                execution_job_id=job_id,
                status=result_status,
                row_count=row_count,
                duration_seconds=duration_seconds,
                snapshot_path=snapshot_path,
                error_message=error_message,
            )
            session.add(result)
            if job.batch_id:
                _update_batch_on_job_finish(session, job.batch_id, True)
            session.commit()
            logger.info("Job %s success (rows=%s, duration=%.2fs)", job_id, row_count, duration_seconds)
        else:
            if job.retry_count < job.max_retries:
                job.status = ExecutionJobStatus.queued.value
                job.retry_count += 1
                job.finished_at = None
                session.commit()
                QueueService().push(job_id, payload)
                logger.warning("Job %s failed (retry %s/%s), requeued: %s", job_id, job.retry_count, job.max_retries, error_message)
            else:
                job.status = ExecutionJobStatus.failed.value
                result = ExecutionResult(
                    execution_job_id=job_id,
                    status=ExecutionResultStatus.failed.value,
                    error_message=error_message,
                )
                session.add(result)
                if job.batch_id:
                    _update_batch_on_job_finish(session, job.batch_id, False)
                session.commit()
                logger.warning("Job %s failed (final): %s", job_id, error_message)
    except Exception as e:
        logger.exception("Job %s exception: %s", job_id, e)
        job.status = ExecutionJobStatus.failed.value
        job.finished_at = datetime.now(timezone.utc)
        if job.retry_count < job.max_retries:
            job.status = ExecutionJobStatus.queued.value
            job.retry_count += 1
            job.finished_at = None
            session.commit()
            QueueService().push(job_id, payload)
            logger.warning("Job %s exception (retry %s/%s), requeued", job_id, job.retry_count, job.max_retries)
        else:
            result = ExecutionResult(
                execution_job_id=job_id,
                status=ExecutionResultStatus.failed.value,
                error_message=str(e),
            )
            session.add(result)
            if job.batch_id:
                _update_batch_on_job_finish(session, job.batch_id, False)
            session.commit()
    finally:
        import shutil
        if config_dir.exists():
            shutil.rmtree(config_dir, ignore_errors=True)


def run_worker_loop() -> None:
    """Main loop: pop from queue, process one job at a time. Run multiple processes for concurrency."""
    s = get_settings()
    redis_display = s.REDIS_URL.split("@")[-1] if "@" in s.REDIS_URL else s.REDIS_URL
    logger.info("Worker starting (Redis=%s, STEAMPIPE_DATABASE_INSECURE=%s)", redis_display, getattr(s, "STEAMPIPE_DATABASE_INSECURE", False))
    try:
        queue = QueueService()
        depth = queue.queue_depth()
        logger.info("Queue depth: %s", depth)
    except Exception as e:
        logger.exception("Failed to connect to Redis: %s", e)
        raise
    factory = get_db_session_factory()
    logger.info("Worker loop started, waiting for jobs (blpop timeout=5s) ...")

    while True:
        payload = queue.pop(timeout_seconds=5)
        if payload is None:
            continue
        job_id = payload.get("job_id")
        if not job_id:
            logger.warning("Popped payload missing job_id: %s", payload)
            continue
        session = factory()
        try:
            process_job(session, job_id, payload)
        finally:
            session.close()
