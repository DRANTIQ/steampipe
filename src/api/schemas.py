"""Pydantic schemas for API request/response."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---- Tenant ----
class TenantCreate(BaseModel):
    name: str
    description: str | None = None
    plan_type: str = "free"
    max_accounts: int = 5
    max_queries: int = 20
    max_executions_per_day: int = 100


class TenantResponse(BaseModel):
    id: str
    name: str
    description: str | None
    plan_type: str
    max_accounts: int
    max_queries: int
    max_executions_per_day: int
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---- CloudAccount ----
class CloudAccountCreate(BaseModel):
    provider: str
    account_id: str
    region: str | None = None
    name: str | None = None
    secret_arn: str | None = None
    extra_metadata: dict[str, Any] | None = None


class CloudAccountResponse(BaseModel):
    id: str
    tenant_id: str
    provider: str
    account_id: str
    region: str | None
    name: str | None
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Query ----
class QueryCreate(BaseModel):
    name: str
    version: str = "1.0"
    provider: str
    plugin: str
    query_text: str
    execution_mode: str = "single_account"
    output_format: str = "json"
    schedule_enabled: bool = False
    extra_metadata: dict[str, Any] | None = None


class QueryResponse(BaseModel):
    id: str
    name: str
    version: str
    provider: str
    plugin: str
    query_text: str
    execution_mode: str
    output_format: str
    schedule_enabled: bool
    active: bool
    content_hash: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Schedule ----
class ScheduleCreate(BaseModel):
    tenant_id: str | None = None
    query_id: str
    cron_expression: str
    timezone: str = "UTC"
    enabled: bool = True


class ScheduleResponse(BaseModel):
    id: str
    tenant_id: str
    query_id: str
    cron_expression: str
    timezone: str
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Execution ----
class ExecutionCreate(BaseModel):
    tenant_id: str
    account_id: str
    query_id: str
    priority: int = 0
    triggered_by: str | None = None


class ExecutionBulkCreate(BaseModel):
    """Run multiple queries for a single account in one request. Creates one job per query."""
    tenant_id: str
    account_id: str
    query_ids: list[str]
    priority: int = 0
    triggered_by: str | None = None


class ExecutionResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime


class ExecutionBulkResponse(BaseModel):
    job_ids: list[str]
    status: str
    created_at: datetime


class ExecutionTriggerTenantCreate(BaseModel):
    """Trigger run for a tenant: all queries on all accounts (all providers). Creates jobs in batches."""
    tenant_id: str
    priority: int = 0
    triggered_by: str | None = None


class ExecutionTriggerTenantResponse(BaseModel):
    batch_id: str
    total_jobs: int
    jobs_created: int
    accounts_count: int
    queries_count: int
    status: str = "queued"
    created_at: datetime


class ExecutionBatchProgressResponse(BaseModel):
    """Batch progress: total / completed / failed counts and status."""
    id: str
    tenant_id: str
    schedule_id: str | None
    trigger_type: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    status: str
    created_at: datetime
    finished_at: datetime | None

    class Config:
        from_attributes = True


class ExecutionJobDetail(BaseModel):
    id: str
    tenant_id: str
    account_id: str
    query_id: str
    status: str
    retry_count: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True


class ExecutionResultResponse(BaseModel):
    id: str
    execution_job_id: str
    status: str
    row_count: int | None
    duration_seconds: float | None
    snapshot_path: str | None
    error_message: str | None
    created_at: datetime

    class Config:
        from_attributes = True
