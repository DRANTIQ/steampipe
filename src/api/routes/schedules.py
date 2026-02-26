from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query as Q

from src.api.deps import DbSession
from src.api.schemas import ScheduleCreate, ScheduleResponse
from src.models import Query, QuerySchedule, Tenant
from src.scheduler.cron_scheduler import compute_next_run

router = APIRouter()


@router.post("", response_model=ScheduleResponse)
def create_schedule(session: DbSession, body: ScheduleCreate) -> QuerySchedule:
    query = session.query(Query).filter(Query.id == body.query_id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    tenant_id = body.tenant_id
    if not tenant_id:
        # Use first tenant as default for demo; in production require from auth
        tenant = session.query(Tenant).filter(Tenant.deleted_at.is_(None)).first()
        if not tenant:
            raise HTTPException(status_code=400, detail="No tenant; provide tenant_id")
        tenant_id = tenant.id
    next_run = compute_next_run(body.cron_expression, body.timezone)
    s = QuerySchedule(
        id=str(uuid4()),
        tenant_id=tenant_id,
        query_id=body.query_id,
        cron_expression=body.cron_expression,
        timezone=body.timezone,
        enabled=body.enabled,
        next_run_at=next_run,
    )
    session.add(s)
    session.flush()
    return s


@router.get("", response_model=list[ScheduleResponse])
def list_schedules(
    session: DbSession,
    tenant_id: str | None = Q(None),
    skip: int = Q(0, ge=0),
    limit: int = Q(20, ge=1, le=100),
    enabled: bool | None = None,
) -> list[QuerySchedule]:
    q = session.query(QuerySchedule)
    if tenant_id:
        q = q.filter(QuerySchedule.tenant_id == tenant_id)
    if enabled is not None:
        q = q.filter(QuerySchedule.enabled == enabled)
    return q.offset(skip).limit(limit).all()
