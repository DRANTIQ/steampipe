"""Platform ops endpoints (super_admin only, T-035)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from src.api.deps import DbSession, require_super_admin
from src.api.schemas import (
    OpsBatchStatusCount,
    OpsFailedJob,
    OpsJobStatusCount,
    OpsJobsSummaryResponse,
    OpsJobsWindow,
    OpsPlatformCounts,
    OpsQueueDepth,
    OpsQueuesResponse,
    OpsRecentBatch,
    OpsStuckBatchResponse,
    OpsSummaryResponse,
)
from src.models import CloudAccount, ExecutionBatch, ExecutionJob, QuerySchedule, Tenant
from src.models.enums import ExecutionJobStatus
from src.services.queue import OPS_QUEUE_KEYS, QueueService

router = APIRouter(dependencies=[Depends(require_super_admin)])

_IN_FLIGHT = {
    ExecutionJobStatus.queued.value,
    ExecutionJobStatus.running.value,
    ExecutionJobStatus.retrying.value,
}


def _age_minutes(since: datetime, now: datetime) -> float:
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return round((now - since).total_seconds() / 60, 1)


def _progress_pct(completed: int, failed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(min(100.0, (completed + failed) / total * 100), 1)


def _batch_response(batch: ExecutionBatch, now: datetime) -> OpsStuckBatchResponse:
    tenant_name = batch.tenant.name if batch.tenant else None
    return OpsStuckBatchResponse(
        id=batch.id,
        tenant_id=batch.tenant_id,
        tenant_name=tenant_name,
        status=batch.status,
        trigger_type=batch.trigger_type,
        total_jobs=batch.total_jobs,
        completed_jobs=batch.completed_jobs,
        failed_jobs=batch.failed_jobs,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
        age_minutes=_age_minutes(batch.created_at, now),
    )


def _recent_batch(batch: ExecutionBatch) -> OpsRecentBatch:
    return OpsRecentBatch(
        id=batch.id,
        tenant_id=batch.tenant_id,
        tenant_name=batch.tenant.name if batch.tenant else None,
        status=batch.status,
        trigger_type=batch.trigger_type,
        total_jobs=batch.total_jobs,
        completed_jobs=batch.completed_jobs,
        failed_jobs=batch.failed_jobs,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
        progress_pct=_progress_pct(batch.completed_jobs, batch.failed_jobs, batch.total_jobs),
    )


@router.get("/queues", response_model=OpsQueuesResponse)
def get_queue_depths() -> OpsQueuesResponse:
    queue = QueueService()
    depths = queue.ops_queue_depths()
    return OpsQueuesResponse(
        redis_ok=queue.ping_ok(),
        queues=[
            OpsQueueDepth(name=name, key=key, depth=depths.get(name, 0))
            for name, key in OPS_QUEUE_KEYS
        ],
    )


@router.get("/jobs/summary", response_model=OpsJobsSummaryResponse)
def get_jobs_summary(session: DbSession) -> OpsJobsSummaryResponse:
    rows = (
        session.query(ExecutionJob.status, func.count())
        .group_by(ExecutionJob.status)
        .order_by(ExecutionJob.status)
        .all()
    )
    return OpsJobsSummaryResponse(
        by_status=[OpsJobStatusCount(status=status, count=count) for status, count in rows]
    )


@router.get("/batches/stuck", response_model=list[OpsStuckBatchResponse])
def list_stuck_batches(
    session: DbSession,
    older_than_minutes: int = Query(30, ge=5, le=24 * 60),
    limit: int = Query(50, ge=1, le=200),
) -> list[OpsStuckBatchResponse]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=older_than_minutes)
    batches = (
        session.query(ExecutionBatch)
        .options(joinedload(ExecutionBatch.tenant))
        .filter(
            ExecutionBatch.status.in_(("running", "queued")),
            ExecutionBatch.created_at < cutoff,
        )
        .order_by(ExecutionBatch.created_at.asc())
        .limit(limit)
        .all()
    )
    return [_batch_response(b, now) for b in batches]


@router.get("/summary", response_model=OpsSummaryResponse)
def get_ops_summary(
    session: DbSession,
    older_than_minutes: int = Query(30, ge=5, le=24 * 60),
    stuck_limit: int = Query(50, ge=1, le=200),
    recent_batch_limit: int = Query(15, ge=1, le=50),
    failed_job_limit: int = Query(20, ge=1, le=100),
) -> OpsSummaryResponse:
    now = datetime.now(timezone.utc)
    cutoff_stuck = now - timedelta(minutes=older_than_minutes)
    cutoff_24h = now - timedelta(hours=24)

    queue = QueueService()
    depths = queue.ops_queue_depths()

    job_status_rows = (
        session.query(ExecutionJob.status, func.count())
        .group_by(ExecutionJob.status)
        .order_by(ExecutionJob.status)
        .all()
    )
    status_map = {status: count for status, count in job_status_rows}
    in_flight = sum(status_map.get(s, 0) for s in _IN_FLIGHT)

    jobs_24h = (
        session.query(ExecutionJob.status, func.count())
        .filter(ExecutionJob.created_at >= cutoff_24h)
        .group_by(ExecutionJob.status)
        .all()
    )
    jobs_24h_map = {status: count for status, count in jobs_24h}
    last_24h_total = sum(jobs_24h_map.values())
    last_24h_success = jobs_24h_map.get(ExecutionJobStatus.success.value, 0)
    last_24h_failed = jobs_24h_map.get(ExecutionJobStatus.failed.value, 0)

    batch_status_rows = (
        session.query(ExecutionBatch.status, func.count())
        .group_by(ExecutionBatch.status)
        .order_by(ExecutionBatch.status)
        .all()
    )

    recent_batches = (
        session.query(ExecutionBatch)
        .options(joinedload(ExecutionBatch.tenant))
        .order_by(ExecutionBatch.created_at.desc())
        .limit(recent_batch_limit)
        .all()
    )

    stuck_batches = (
        session.query(ExecutionBatch)
        .options(joinedload(ExecutionBatch.tenant))
        .filter(
            ExecutionBatch.status.in_(("running", "queued")),
            ExecutionBatch.created_at < cutoff_stuck,
        )
        .order_by(ExecutionBatch.created_at.asc())
        .limit(stuck_limit)
        .all()
    )

    failed_jobs = (
        session.query(ExecutionJob)
        .options(joinedload(ExecutionJob.tenant), joinedload(ExecutionJob.result))
        .filter(ExecutionJob.status == ExecutionJobStatus.failed.value)
        .order_by(ExecutionJob.finished_at.desc().nullslast(), ExecutionJob.created_at.desc())
        .limit(failed_job_limit)
        .all()
    )

    tenant_count = session.query(func.count(Tenant.id)).filter(Tenant.deleted_at.is_(None)).scalar() or 0
    active_tenant_count = (
        session.query(func.count(Tenant.id))
        .filter(Tenant.deleted_at.is_(None), Tenant.active.is_(True))
        .scalar()
        or 0
    )
    account_count = session.query(func.count(CloudAccount.id)).scalar() or 0
    schedule_count = session.query(func.count(QuerySchedule.id)).scalar() or 0
    batches_running = (
        session.query(func.count(ExecutionBatch.id))
        .filter(ExecutionBatch.status.in_(("running", "queued")))
        .scalar()
        or 0
    )

    return OpsSummaryResponse(
        checked_at=now,
        redis_ok=queue.ping_ok(),
        queues=[
            OpsQueueDepth(name=name, key=key, depth=depths.get(name, 0))
            for name, key in OPS_QUEUE_KEYS
        ],
        platform=OpsPlatformCounts(
            tenants=tenant_count,
            active_tenants=active_tenant_count,
            cloud_accounts=account_count,
            schedules=schedule_count,
            batches_running=batches_running,
            account_session_locks=queue.count_account_session_locks(),
        ),
        jobs=OpsJobsWindow(
            last_24h_total=last_24h_total,
            last_24h_success=last_24h_success,
            last_24h_failed=last_24h_failed,
            in_flight=in_flight,
        ),
        jobs_by_status=[
            OpsJobStatusCount(status=status, count=count) for status, count in job_status_rows
        ],
        batches_by_status=[
            OpsBatchStatusCount(status=status, count=count) for status, count in batch_status_rows
        ],
        recent_batches=[_recent_batch(b) for b in recent_batches],
        stuck_batches=[_batch_response(b, now) for b in stuck_batches],
        recent_failed_jobs=[
            OpsFailedJob(
                id=j.id,
                tenant_id=j.tenant_id,
                tenant_name=j.tenant.name if j.tenant else None,
                account_id=j.account_id,
                query_id=j.query_id,
                batch_id=j.batch_id,
                status=j.status,
                retry_count=j.retry_count,
                finished_at=j.finished_at,
                error_message=j.result.error_message if j.result else None,
            )
            for j in failed_jobs
        ],
    )
