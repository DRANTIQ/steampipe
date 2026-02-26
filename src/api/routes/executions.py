from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query as Q
from sqlalchemy import func

from src.api.deps import DbSession
from src.api.schemas import (
    ExecutionCreate,
    ExecutionBulkCreate,
    ExecutionTriggerTenantCreate,
    ExecutionTriggerTenantResponse,
    ExecutionBatchProgressResponse,
    ExecutionResponse,
    ExecutionBulkResponse,
    ExecutionJobDetail,
    ExecutionResultResponse,
)
from src.config import get_settings
from src.models import ExecutionBatch, ExecutionJob, ExecutionResult, Tenant, CloudAccount, Query
from src.models.enums import ExecutionJobStatus
from src.services.queue import QueueService
from src.services.snapshot import SnapshotService

router = APIRouter()

CHUNK_SIZE = 200  # align with BULK_QUERY_IDS_MAX


def _count_tenant_jobs_today(session: DbSession, tenant_id: str) -> int:
    """Count execution jobs created today for this tenant (UTC)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.query(func.count(ExecutionJob.id))
        .filter(ExecutionJob.tenant_id == tenant_id, ExecutionJob.created_at >= today_start)
        .scalar()
        or 0
    )


def _check_tenant_limits(session: DbSession, tenant_id: str) -> Tenant:
    tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.active:
        raise HTTPException(status_code=403, detail="Tenant is inactive")
    return tenant


@router.post("", response_model=ExecutionResponse)
def create_execution(session: DbSession, body: ExecutionCreate) -> ExecutionResponse:
    _check_tenant_limits(session, body.tenant_id)
    # batch_id left null for single execution
    account = (
        session.query(CloudAccount)
        .filter(
            CloudAccount.id == body.account_id,
            CloudAccount.tenant_id == body.tenant_id,
            CloudAccount.deleted_at.is_(None),
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    query = session.query(Query).filter(Query.id == body.query_id, Query.deleted_at.is_(None)).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    job_id = str(uuid4())
    job = ExecutionJob(
        id=job_id,
        tenant_id=body.tenant_id,
        account_id=body.account_id,
        query_id=body.query_id,
        priority=body.priority,
        status=ExecutionJobStatus.queued.value,
        triggered_by=body.triggered_by,
    )
    session.add(job)
    session.flush()

    queue = QueueService()
    queue.push(job_id, {"tenant_id": body.tenant_id, "account_id": body.account_id, "query_id": body.query_id})

    return ExecutionResponse(
        job_id=job_id,
        status=ExecutionJobStatus.queued.value,
        created_at=job.created_at,
    )


@router.post("/bulk", response_model=ExecutionBulkResponse)
def create_executions_bulk(session: DbSession, body: ExecutionBulkCreate) -> ExecutionBulkResponse:
    """Create one execution job per query for the same account. All jobs are queued; worker processes each independently."""
    if not body.query_ids:
        raise HTTPException(status_code=400, detail="query_ids must not be empty")
    _check_tenant_limits(session, body.tenant_id)
    account = (
        session.query(CloudAccount)
        .filter(
            CloudAccount.id == body.account_id,
            CloudAccount.tenant_id == body.tenant_id,
            CloudAccount.deleted_at.is_(None),
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    # Resolve all query ids
    queries = session.query(Query).filter(
        Query.id.in_(body.query_ids),
        Query.deleted_at.is_(None),
    ).all()
    found_ids = {q.id for q in queries}
    missing = set(body.query_ids) - found_ids
    if missing:
        raise HTTPException(status_code=404, detail=f"Queries not found: {sorted(missing)}")
    queue = QueueService()
    job_ids: list[str] = []
    for query in queries:
        job_id = str(uuid4())
        job = ExecutionJob(
            id=job_id,
            tenant_id=body.tenant_id,
            account_id=body.account_id,
            query_id=query.id,
            priority=body.priority,
            status=ExecutionJobStatus.queued.value,
            triggered_by=body.triggered_by or "bulk",
        )
        session.add(job)
        session.flush()
        queue.push(job_id, {"tenant_id": body.tenant_id, "account_id": body.account_id, "query_id": query.id})
        job_ids.append(job_id)
    return ExecutionBulkResponse(
        job_ids=job_ids,
        status=ExecutionJobStatus.queued.value,
        created_at=datetime.now(timezone.utc),
    )


@router.post("/trigger-tenant", response_model=ExecutionTriggerTenantResponse)
def trigger_tenant(session: DbSession, body: ExecutionTriggerTenantCreate) -> ExecutionTriggerTenantResponse:
    """Run all queries on all accounts for a tenant (all providers). Creates a batch and jobs in chunks of 200."""
    tenant = _check_tenant_limits(session, body.tenant_id)
    accounts = (
        session.query(CloudAccount)
        .filter(
            CloudAccount.tenant_id == body.tenant_id,
            CloudAccount.active == True,
            CloudAccount.deleted_at.is_(None),
        )
        .all()
    )
    queries = (
        session.query(Query)
        .filter(Query.active == True, Query.deleted_at.is_(None))
        .all()
    )
    pairs: list[tuple[CloudAccount, Query]] = []
    for account in accounts:
        for query in queries:
            if account.provider == query.provider:
                pairs.append((account, query))
    total_jobs = len(pairs)
    if total_jobs == 0:
        return ExecutionTriggerTenantResponse(
            batch_id="",
            total_jobs=0,
            jobs_created=0,
            accounts_count=len(accounts),
            queries_count=len(queries),
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
    today_count = _count_tenant_jobs_today(session, body.tenant_id)
    if today_count + total_jobs > tenant.max_executions_per_day:
        raise HTTPException(
            status_code=429,
            detail=f"Tenant daily execution limit exceeded (max {tenant.max_executions_per_day}, today {today_count}, would add {total_jobs})",
        )
    batch = ExecutionBatch(
        tenant_id=body.tenant_id,
        schedule_id=None,
        scheduled_at=None,
        trigger_type="manual",
        total_jobs=total_jobs,
        status="running",
    )
    session.add(batch)
    session.flush()
    queue = QueueService()
    created = 0
    chunk_size = get_settings().BULK_QUERY_IDS_MAX
    for i in range(0, total_jobs, chunk_size):
        chunk = pairs[i : i + chunk_size]
        for account, query in chunk:
            job_id = str(uuid4())
            job = ExecutionJob(
                id=job_id,
                tenant_id=body.tenant_id,
                account_id=account.id,
                query_id=query.id,
                priority=body.priority,
                status=ExecutionJobStatus.queued.value,
                triggered_by=body.triggered_by or "trigger-tenant",
                batch_id=batch.id,
            )
            session.add(job)
            session.flush()
            queue.push(job_id, {"tenant_id": body.tenant_id, "account_id": account.id, "query_id": query.id})
            created += 1
        session.commit()
    return ExecutionTriggerTenantResponse(
        batch_id=batch.id,
        total_jobs=total_jobs,
        jobs_created=created,
        accounts_count=len(accounts),
        queries_count=len(queries),
        status="queued",
        created_at=batch.created_at,
    )


@router.get(
    "/batches/{batch_id}",
    response_model=ExecutionBatchProgressResponse,
    summary="Get batch progress",
    operation_id="get_execution_batch_progress",
)
def get_batch_progress(session: DbSession, batch_id: str) -> ExecutionBatch:
    """Get batch progress: total_jobs, completed_jobs, failed_jobs, status. Use the batch_id returned by POST /executions/trigger-tenant."""
    batch = session.query(ExecutionBatch).filter(ExecutionBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("", response_model=list[ExecutionJobDetail])
def list_executions(
    session: DbSession,
    tenant_id: str | None = Q(None),
    status: str | None = Q(None),
    skip: int = Q(0, ge=0),
    limit: int = Q(20, ge=1, le=100),
) -> list[ExecutionJob]:
    q = session.query(ExecutionJob)
    if tenant_id:
        q = q.filter(ExecutionJob.tenant_id == tenant_id)
    if status:
        q = q.filter(ExecutionJob.status == status)
    return q.order_by(ExecutionJob.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{job_id}", response_model=ExecutionJobDetail)
def get_execution(session: DbSession, job_id: str) -> ExecutionJob:
    job = session.query(ExecutionJob).filter(ExecutionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Execution job not found")
    return job


def _result_not_found_detail(session: DbSession, job_id: str) -> str:
    job = session.query(ExecutionJob).filter(ExecutionJob.id == job_id).first()
    if not job:
        return "Execution result not found."
    return (
        f"Execution result not found. Job status: {job.status}. "
        f"Poll GET /executions/{job_id} until status is 'success' or 'failed', then retry this endpoint. "
        "If status stays 'running' for a long time, the worker may have restarted."
    )


@router.get("/{job_id}/result", response_model=ExecutionResultResponse)
def get_execution_result(session: DbSession, job_id: str) -> ExecutionResult:
    result = session.query(ExecutionResult).filter(ExecutionResult.execution_job_id == job_id).first()
    if not result:
        raise HTTPException(status_code=404, detail=_result_not_found_detail(session, job_id))
    return result


@router.get("/{job_id}/result/data")
def get_execution_result_data(session: DbSession, job_id: str) -> dict:
    """Return the snapshot JSON (Steampipe result rows). Available once the job has completed successfully."""
    result = session.query(ExecutionResult).filter(ExecutionResult.execution_job_id == job_id).first()
    if not result:
        raise HTTPException(status_code=404, detail=_result_not_found_detail(session, job_id))
    if not result.snapshot_path:
        raise HTTPException(
            status_code=404,
            detail="No snapshot (job may still be running or have failed)",
        )
    content = SnapshotService().get_snapshot_content(result.snapshot_path)
    if content is None:
        raise HTTPException(status_code=404, detail="Snapshot data not found or unreadable")
    return content
