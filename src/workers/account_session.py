"""Account session: one AssumeRole + one Steampipe init per batch/account (Phase C)."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import CloudAccount, ExecutionJob, ExecutionResult, Query, Tenant
from src.models.enums import ExecutionJobStatus, ExecutionResultStatus
from src.services.job_completed_event import build_job_completed_payload
from src.services.queue import QueueService
from src.services.secrets import SecretsService
from src.services.snapshot import SnapshotService
from src.services.snapshot_document import build_snapshot_document
from src.workers.execution_worker import (
    _assume_role_and_get_credentials,
    _conn_config_to_hcl,
    _fail_job_connection,
    _log_aws_creds_and_verify_get_caller_identity,
    _run_steampipe_query,
    _update_batch_on_job_finish,
    _write_assumed_credentials_file,
    _write_aws_credentials_file,
)

logger = logging.getLogger(__name__)


def claim_all_batch_account_jobs(session: Session, batch_id: str, account_id: str) -> list[ExecutionJob]:
    """Claim all queued jobs for a batch+account (single worker, one Steampipe session)."""
    settings = get_settings()
    max_jobs = settings.STEAMPIPE_SESSION_MAX_JOBS
    queued = (
        session.query(ExecutionJob)
        .filter(
            ExecutionJob.batch_id == batch_id,
            ExecutionJob.account_id == account_id,
            ExecutionJob.status == ExecutionJobStatus.queued.value,
        )
        .order_by(ExecutionJob.created_at)
        .limit(max_jobs)
        .all()
    )
    if not queued:
        return []
    now = datetime.now(timezone.utc)
    claimed_ids: list[str] = []
    for job in queued:
        result = session.execute(
            update(ExecutionJob)
            .where(ExecutionJob.id == job.id)
            .where(ExecutionJob.status == ExecutionJobStatus.queued.value)
            .values(status=ExecutionJobStatus.running.value, started_at=now)
        )
        if result.rowcount:
            claimed_ids.append(job.id)
    session.commit()
    jobs = (
        session.query(ExecutionJob)
        .filter(ExecutionJob.id.in_(claimed_ids))
        .order_by(ExecutionJob.created_at)
        .all()
    )
    if jobs:
        logger.info(
            "Account session: batch=%s account=%s claimed %s jobs (one Steampipe init)",
            batch_id,
            account_id,
            len(jobs),
        )
    return jobs


def run_account_session_for_batch(
    session: Session,
    *,
    batch_id: str,
    account_id: str,
    tenant_id: str,
) -> None:
    """Process all queued jobs for (batch_id, account_id). One Redis message → one worker."""
    settings = get_settings()
    if not settings.STEAMPIPE_ACCOUNT_SESSION_ENABLED:
        return

    queue = QueueService()
    if queue.account_session_lock_held(batch_id, account_id):
        queue.push_account_session(batch_id=batch_id, account_id=account_id, tenant_id=tenant_id)
        logger.debug(
            "Account session deferred: batch=%s account=%s (lock held)",
            batch_id,
            account_id,
        )
        return

    if not queue.try_acquire_account_session_lock(batch_id, account_id):
        queue.push_account_session(batch_id=batch_id, account_id=account_id, tenant_id=tenant_id)
        return

    try:
        jobs = claim_all_batch_account_jobs(session, batch_id, account_id)
        if not jobs:
            logger.info(
                "Account session: no queued jobs for batch=%s account=%s",
                batch_id,
                account_id,
            )
            return
        logger.info(
            "Processing account session (batch=%s, account=%s, jobs=%s)",
            batch_id,
            account_id,
            len(jobs),
        )
        process_account_session(session, jobs)
    finally:
        queue.release_account_session_lock(batch_id, account_id)



def _setup_aws_config(
    session: Session,
    job: ExecutionJob,
    account: CloudAccount,
    config_dir: Path,
    config_subdir: Path,
    query: Query,
) -> tuple[str, dict[str, str], str] | None:
    """Assume role / write creds and .spc. Returns (connection_name, extra_env, error) or None on failure."""
    secrets_service = SecretsService()
    conn_config = secrets_service.get_connection_config(
        account.id, account.provider, account.secret_arn, account.extra_metadata
    )
    extra_env: dict[str, str] = {}
    job_id = job.id

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
                    "Assume-role is configured but master credentials are missing.",
                )
                return None
            logger.info("Session %s: assuming role role_arn=%s", job.batch_id, role_arn)
            assumed = _assume_role_and_get_credentials(
                role_arn,
                external_id,
                account.region,
                role_session_name=f"steampipe-{job.batch_id[:8]}",
            )
            if not assumed:
                _fail_job_connection(session, job, job_id, "Failed to assume role.")
                return None
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
        else:
            if not _write_aws_credentials_file(config_dir):
                _fail_job_connection(session, job, job_id, "AWS credentials not found in worker environment.")
                return None
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

    spc = config_subdir / f"{account.provider}.spc"
    raw_name = conn_config.get("connection_name", f"{account.provider}_{account.id}")
    connection_name = raw_name.replace("-", "_").replace(" ", "_")
    body = _conn_config_to_hcl(conn_config, query.plugin)
    spc.write_text(f'connection "{connection_name}" {{\n{body}\n}}\n')
    return connection_name, extra_env, ""


def _publish_completed(job: ExecutionJob, query: Query, snapshot_path: str | None, row_count: int) -> None:
    meta = query.extra_metadata if isinstance(query.extra_metadata, dict) else {}
    try:
        QueueService().publish_job_completed(
            build_job_completed_payload(
                job_id=job.id,
                snapshot_path=snapshot_path,
                tenant_id=job.tenant_id,
                account_id=job.account_id,
                query_id=job.query_id,
                batch_id=job.batch_id,
                extra_metadata=meta,
                row_count=row_count,
            )
        )
    except Exception as pub_err:
        logger.warning("Job %s: failed to publish job_completed event: %s", job.id, pub_err)


def process_account_session(session: Session, jobs: list[ExecutionJob]) -> None:
    """Run all jobs in one Steampipe session (single init, many queries)."""
    if not jobs:
        return

    settings = get_settings()
    lead = jobs[0]
    account = session.query(CloudAccount).filter(CloudAccount.id == lead.account_id).first()
    tenant = session.query(Tenant).filter(Tenant.id == lead.tenant_id).first()
    first_query = session.query(Query).filter(Query.id == lead.query_id).first()
    if not account or not first_query:
        _fail_job_connection(session, lead, lead.id, "Account or query not found for session")
        for job in jobs[1:]:
            _fail_job_connection(session, job, job.id, "Account or query not found for session")
        return

    batch_key = lead.batch_id or lead.id
    config_dir = Path(settings.STEAMPIPE_CONFIG_DIR) / f"session_{batch_key}_{lead.account_id[:8]}"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_subdir = config_dir / "config"
    config_subdir.mkdir(parents=True, exist_ok=True)
    port = getattr(settings, "STEAMPIPE_DATABASE_PORT", 9194)
    (config_subdir / "default.spc").write_text(f'options "database" {{\n  port = {port}\n}}\n')

    setup = _setup_aws_config(session, lead, account, config_dir, config_subdir, first_query)
    if setup is None:
        for job in jobs[1:]:
            _fail_job_connection(session, job, job.id, "Session setup failed")
        return
    connection_name, extra_env, _ = setup

    snapshot_service = SnapshotService()
    total = len(jobs)

    try:
        for idx, job in enumerate(jobs):
            query = session.query(Query).filter(Query.id == job.query_id).first()
            if not query:
                _fail_job_connection(session, job, job.id, "Query not found")
                continue

            is_first = idx == 0
            is_last = idx == total - 1
            output, row_count, duration_seconds, error_message = _run_steampipe_query(
                query.query_text,
                query.plugin,
                query.output_format,
                config_dir,
                settings.STEAMPIPE_PATH,
                connection_name=connection_name,
                extra_env=extra_env or None,
                skip_service_start=not is_first,
                keep_service_alive=not is_last,
            )

            job.finished_at = datetime.now(timezone.utc)
            if error_message:
                job.status = ExecutionJobStatus.failed.value
                session.add(
                    ExecutionResult(
                        execution_job_id=job.id,
                        status=ExecutionResultStatus.failed.value,
                        error_message=error_message,
                    )
                )
                if job.batch_id:
                    _update_batch_on_job_finish(session, job.batch_id, False)
                session.commit()
                logger.warning("Job %s failed in session: %s", job.id, error_message[:200])
                continue

            meta = query.extra_metadata if isinstance(query.extra_metadata, dict) else {}
            raw_output = output if isinstance(output, dict) else {"rows": output}
            snapshot_payload = build_snapshot_document(
                steampipe_output=raw_output,
                execution_job_id=job.id,
                query_id=job.query_id,
                query_name=query.name,
                tenant_id=job.tenant_id,
                account_id=job.account_id,
                provider=account.provider,
                batch_id=job.batch_id,
                extra_metadata=meta,
            )
            snapshot_path = snapshot_service.persist_snapshot(
                tenant_id=job.tenant_id,
                tenant_name=tenant.name if tenant else None,
                execution_id=job.id,
                query_id=job.query_id,
                account_id=job.account_id,
                provider=account.provider,
                account_identifier=account.account_id,
                region=account.region,
                data=snapshot_payload,
                batch_id=job.batch_id,
            )
            job.status = ExecutionJobStatus.success.value
            session.add(
                ExecutionResult(
                    execution_job_id=job.id,
                    status=ExecutionResultStatus.success.value,
                    row_count=row_count,
                    duration_seconds=duration_seconds,
                    snapshot_path=snapshot_path,
                )
            )
            if job.batch_id:
                _update_batch_on_job_finish(session, job.batch_id, True)
            session.commit()
            logger.info(
                "Job %s success in session (%s/%s, rows=%s, duration=%.2fs)",
                job.id,
                idx + 1,
                total,
                row_count,
                duration_seconds,
            )
            _publish_completed(job, query, snapshot_path, row_count)
    finally:
        if config_dir.exists():
            shutil.rmtree(config_dir, ignore_errors=True)
