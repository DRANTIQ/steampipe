"""Scheduler: poll QuerySchedule, enqueue execution jobs. Does NOT run Steampipe."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from croniter import croniter

from src.config import get_settings
from src.models import CloudAccount, ExecutionBatch, ExecutionJob, Query, QuerySchedule
from src.models.enums import ExecutionJobStatus
from src.services.database import get_db_session_factory
from src.services.queue import QueueService

CHUNK_SIZE = 200  # align with BULK_QUERY_IDS_MAX


def compute_next_run(cron_expression: str, timezone_name: str) -> datetime | None:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    it = croniter(cron_expression, now)
    return it.get_next(datetime).astimezone(timezone.utc)


def run_scheduled_jobs() -> None:
    """Fetch schedules due to run, create ExecutionBatch and jobs in chunks, push to Redis, update next_run_at."""
    factory = get_db_session_factory()
    session = factory()
    try:
        now = datetime.now(timezone.utc)
        schedules = (
            session.query(QuerySchedule)
            .filter(
                QuerySchedule.enabled == True,
                QuerySchedule.next_run_at.isnot(None),
                QuerySchedule.next_run_at <= now,
            )
            .all()
        )
        queue = QueueService()
        for s in schedules:
            scheduled_at = s.next_run_at
            # Idempotency: skip if batch already exists for this schedule and scheduled time
            existing = (
                session.query(ExecutionBatch)
                .filter(
                    ExecutionBatch.schedule_id == s.id,
                    ExecutionBatch.scheduled_at == scheduled_at,
                )
                .first()
            )
            if existing:
                s.last_run_at = scheduled_at
                s.next_run_at = compute_next_run(s.cron_expression, s.timezone)
                continue

            if s.run_all:
                # Load all active queries; build (account, query) pairs where provider matches
                accounts = (
                    session.query(CloudAccount)
                    .filter(
                        CloudAccount.tenant_id == s.tenant_id,
                        CloudAccount.deleted_at.is_(None),
                        CloudAccount.active == True,
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
            else:
                # Single query: query_id must be set when run_all is false
                if not s.query_id:
                    s.last_run_at = scheduled_at
                    s.next_run_at = compute_next_run(s.cron_expression, s.timezone)
                    continue
                query = session.query(Query).filter(Query.id == s.query_id).first()
                if not query:
                    s.last_run_at = scheduled_at
                    s.next_run_at = compute_next_run(s.cron_expression, s.timezone)
                    continue
                accounts = (
                    session.query(CloudAccount)
                    .filter(
                        CloudAccount.tenant_id == s.tenant_id,
                        CloudAccount.provider == query.provider,
                        CloudAccount.deleted_at.is_(None),
                        CloudAccount.active == True,
                    )
                    .all()
                )
                pairs = [(acc, query) for acc in accounts]

            if not pairs:
                s.last_run_at = scheduled_at
                s.next_run_at = compute_next_run(s.cron_expression, s.timezone)
                continue

            batch = ExecutionBatch(
                tenant_id=s.tenant_id,
                schedule_id=s.id,
                scheduled_at=scheduled_at,
                trigger_type="schedule",
                total_jobs=len(pairs),
                status="running",
            )
            session.add(batch)
            session.flush()

            for i in range(0, len(pairs), CHUNK_SIZE):
                chunk = pairs[i : i + CHUNK_SIZE]
                for account, query in chunk:
                    job_id = str(uuid4())
                    job = ExecutionJob(
                        id=job_id,
                        tenant_id=s.tenant_id,
                        account_id=account.id,
                        query_id=query.id,
                        status=ExecutionJobStatus.queued.value,
                        triggered_by="scheduler",
                        scheduled_at=scheduled_at,
                        batch_id=batch.id,
                    )
                    session.add(job)
                    session.flush()
                    queue.push(job_id, {"tenant_id": s.tenant_id, "account_id": account.id, "query_id": query.id})
                session.commit()

            s.last_run_at = scheduled_at
            s.next_run_at = compute_next_run(s.cron_expression, s.timezone)
        session.commit()
    finally:
        session.close()


def run_scheduler() -> None:
    """Run APScheduler: every minute call run_scheduled_jobs."""
    if not get_settings().SCHEDULER_ENABLED:
        return
    scheduler = BlockingScheduler()
    scheduler.add_job(run_scheduled_jobs, IntervalTrigger(minutes=1), id="steampipe_schedules")
    scheduler.start()
