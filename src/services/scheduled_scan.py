"""Scheduled CIS / framework scans (T-030)."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from src.models import CloudAccount, ExecutionBatch, ExecutionJob, Query, QuerySchedule
from src.models.enums import ExecutionJobStatus
from src.services.execution_batch_service import (
    create_execution_batch,
    dispatch_batch_account_queue,
    enqueue_jobs_for_account,
)
from src.services.query_catalog import filter_queries
from src.services.queue import QueueService

SCHEDULE_KIND_QUERY = "query"
SCHEDULE_KIND_FRAMEWORK_SCAN = "framework_scan"


def get_framework_queries_for_account(
    session: Session,
    account: CloudAccount,
    *,
    framework_id: str,
    category: str = "compliance",
) -> list[Query]:
    all_queries = session.query(Query).filter(Query.deleted_at.is_(None)).all()
    return filter_queries(
        all_queries,
        provider=account.provider,
        category=category,
        framework_id=framework_id,
        exclude_legacy=True,
    )


def get_schedule_target_accounts(session: Session, schedule: QuerySchedule) -> list[CloudAccount]:
    q = session.query(CloudAccount).filter(
        CloudAccount.tenant_id == schedule.tenant_id,
        CloudAccount.deleted_at.is_(None),
        CloudAccount.active == True,
    )
    if schedule.account_id:
        q = q.filter(CloudAccount.id == schedule.account_id)
    return q.all()


def _batch_exists_for_account(
    session: Session,
    *,
    schedule_id: str,
    scheduled_at: datetime,
    account_id: str,
) -> bool:
    return (
        session.query(ExecutionJob.id)
        .join(ExecutionBatch, ExecutionJob.batch_id == ExecutionBatch.id)
        .filter(
            ExecutionBatch.schedule_id == schedule_id,
            ExecutionBatch.scheduled_at == scheduled_at,
            ExecutionJob.account_id == account_id,
        )
        .first()
        is not None
    )


def run_framework_scan_schedule(
    session: Session,
    schedule: QuerySchedule,
    scheduled_at: datetime,
    queue: QueueService,
) -> list[str]:
    """
    Enqueue one execution batch per target account (same as POST /executions/scan).
    Returns batch ids created this tick.
    """
    if not schedule.framework_id:
        return []

    accounts = get_schedule_target_accounts(session, schedule)
    batch_ids: list[str] = []

    for account in accounts:
        if _batch_exists_for_account(
            session,
            schedule_id=schedule.id,
            scheduled_at=scheduled_at,
            account_id=account.id,
        ):
            continue

        queries = get_framework_queries_for_account(
            session,
            account,
            framework_id=schedule.framework_id,
            category=schedule.category or "compliance",
        )
        if not queries:
            continue

        batch = create_execution_batch(
            session,
            schedule.tenant_id,
            total_jobs=len(queries),
            trigger_type="schedule",
            schedule_id=schedule.id,
            scheduled_at=scheduled_at,
        )
        job_ids = enqueue_jobs_for_account(
            session,
            tenant_id=schedule.tenant_id,
            account_id=account.id,
            queries=queries,
            batch_id=batch.id,
            triggered_by="scheduler",
        )
        session.commit()
        dispatch_batch_account_queue(
            queue,
            tenant_id=schedule.tenant_id,
            account_id=account.id,
            batch_id=batch.id,
            job_ids=job_ids,
        )
        batch_ids.append(batch.id)

    return batch_ids


def create_framework_scan_schedule(
    session: Session,
    *,
    tenant_id: str,
    cron_expression: str,
    framework_id: str = "cis_aws_v6",
    category: str = "compliance",
    account_id: str | None = None,
    timezone: str = "UTC",
    enabled: bool = True,
    next_run_at: datetime | None,
) -> QuerySchedule:
    schedule = QuerySchedule(
        id=str(uuid4()),
        tenant_id=tenant_id,
        query_id=None,
        account_id=account_id,
        schedule_kind=SCHEDULE_KIND_FRAMEWORK_SCAN,
        framework_id=framework_id,
        category=category,
        run_all=False,
        cron_expression=cron_expression,
        timezone=timezone,
        enabled=enabled,
        next_run_at=next_run_at,
    )
    session.add(schedule)
    session.flush()
    return schedule
