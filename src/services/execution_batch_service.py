"""Create execution batches and enqueue jobs (bulk, scan, trigger-tenant)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import ExecutionBatch, ExecutionJob, Query
from src.models.enums import ExecutionJobStatus
from src.services.queue import QueueService


def create_execution_batch(
    session: Session,
    tenant_id: str,
    total_jobs: int,
    *,
    trigger_type: str = "manual",
    schedule_id: str | None = None,
    scheduled_at: datetime | None = None,
) -> ExecutionBatch:
    batch = ExecutionBatch(
        tenant_id=tenant_id,
        schedule_id=schedule_id,
        scheduled_at=scheduled_at,
        trigger_type=trigger_type,
        total_jobs=total_jobs,
        status="running" if total_jobs > 0 else "completed",
    )
    session.add(batch)
    session.flush()
    return batch


def dispatch_batch_account_queue(
    queue: QueueService,
    *,
    tenant_id: str,
    account_id: str,
    batch_id: str,
    job_ids: list[str],
) -> None:
    """
    Push work to Redis after DB commit.
    Account session mode: one queue message per (batch_id, account_id).
    Legacy mode: one message per job.
    """
    settings = get_settings()
    if settings.STEAMPIPE_ACCOUNT_SESSION_ENABLED and batch_id:
        queue.push_account_session(batch_id=batch_id, account_id=account_id, tenant_id=tenant_id)
        return
    for job_id in job_ids:
        queue.push(
            job_id,
            {
                "tenant_id": tenant_id,
                "account_id": account_id,
                "batch_id": batch_id,
            },
        )


def enqueue_jobs_for_account(
    session: Session,
    *,
    tenant_id: str,
    account_id: str,
    queries: list[Query],
    batch_id: str,
    priority: int = 0,
    triggered_by: str = "bulk",
) -> list[str]:
    """Create one execution job per query in Postgres. Caller must commit then dispatch_batch_account_queue."""
    job_ids: list[str] = []
    for query in queries:
        job_id = str(uuid4())
        job = ExecutionJob(
            id=job_id,
            tenant_id=tenant_id,
            account_id=account_id,
            query_id=query.id,
            priority=priority,
            status=ExecutionJobStatus.queued.value,
            triggered_by=triggered_by,
            batch_id=batch_id,
        )
        session.add(job)
        session.flush()
        job_ids.append(job_id)
    return job_ids


def enqueue_jobs_chunked(
    session: Session,
    queue: QueueService,
    *,
    tenant_id: str,
    pairs: list[tuple[str, Query]],
    batch_id: str,
    priority: int = 0,
    triggered_by: str = "trigger-tenant",
    chunk_size: int = 200,
) -> int:
    """Enqueue (account_id, query) pairs in commits of chunk_size. Returns jobs created."""
    created = 0
    for i in range(0, len(pairs), chunk_size):
        chunk = pairs[i : i + chunk_size]
        account_job_ids: dict[str, list[str]] = defaultdict(list)
        for account_id, query in chunk:
            job_id = str(uuid4())
            job = ExecutionJob(
                id=job_id,
                tenant_id=tenant_id,
                account_id=account_id,
                query_id=query.id,
                priority=priority,
                status=ExecutionJobStatus.queued.value,
                triggered_by=triggered_by,
                batch_id=batch_id,
            )
            session.add(job)
            session.flush()
            account_job_ids[account_id].append(job_id)
            created += 1
        session.commit()
        for account_id, job_ids in account_job_ids.items():
            dispatch_batch_account_queue(
                queue,
                tenant_id=tenant_id,
                account_id=account_id,
                batch_id=batch_id,
                job_ids=job_ids,
            )
    return created
