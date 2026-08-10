"""Pydantic schemas for API request/response."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---- User ----
class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    role: str = "tenant_admin"
    username: str | None = None


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = Field(default=None, min_length=8)
    role: str | None = None
    active: bool | None = None
    username: str | None = None


class UserResponse(BaseModel):
    id: str
    tenant_id: str
    email: str
    username: str | None
    role: str
    active: bool
    last_login: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


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


class ScheduleScanCreate(BaseModel):
    """Cron schedule for full framework scan (e.g. nightly CIS) per account."""
    tenant_id: str
    account_id: str | None = None
    framework_id: str = "cis_aws_v6"
    category: str = "compliance"
    cron_expression: str = "0 2 * * *"
    timezone: str = "UTC"
    enabled: bool = True


class ScheduleResponse(BaseModel):
    id: str
    tenant_id: str
    query_id: str | None
    account_id: str | None = None
    schedule_kind: str = "query"
    framework_id: str | None = None
    category: str | None = None
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


class ExecutionScanCreate(BaseModel):
    """Run all matching catalog queries for one account (e.g. full CIS framework scan)."""
    tenant_id: str
    account_id: str
    framework_id: str | None = Field(
        None,
        description="Catalog key, e.g. cis_aws_v6. Omit to run all queries matching category.",
    )
    category: str = Field("compliance", description="Filter queries by extra_metadata.category")
    priority: int = 0
    triggered_by: str | None = None


class ExecutionResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime


class ExecutionBulkResponse(BaseModel):
    batch_id: str
    job_ids: list[str]
    total_jobs: int
    status: str
    created_at: datetime


class ExecutionScanResponse(BaseModel):
    batch_id: str
    job_ids: list[str]
    total_jobs: int
    framework_id: str | None
    category: str
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


# ---- Ops (super_admin) ----
class OpsQueueDepth(BaseModel):
    name: str
    key: str
    depth: int


class OpsQueuesResponse(BaseModel):
    redis_ok: bool
    queues: list[OpsQueueDepth]


class OpsJobStatusCount(BaseModel):
    status: str
    count: int


class OpsJobsSummaryResponse(BaseModel):
    by_status: list[OpsJobStatusCount]


class OpsStuckBatchResponse(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str | None = None
    status: str
    trigger_type: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    created_at: datetime
    finished_at: datetime | None = None
    age_minutes: float

    class Config:
        from_attributes = True


class OpsBatchStatusCount(BaseModel):
    status: str
    count: int


class OpsRecentBatch(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str | None = None
    status: str
    trigger_type: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    created_at: datetime
    finished_at: datetime | None = None
    progress_pct: float


class OpsFailedJob(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str | None = None
    account_id: str
    query_id: str
    batch_id: str | None = None
    status: str
    retry_count: int
    finished_at: datetime | None = None
    error_message: str | None = None


class OpsPlatformCounts(BaseModel):
    tenants: int
    active_tenants: int
    cloud_accounts: int
    schedules: int
    batches_running: int
    account_session_locks: int


class OpsJobsWindow(BaseModel):
    last_24h_total: int
    last_24h_success: int
    last_24h_failed: int
    in_flight: int


class OpsSummaryResponse(BaseModel):
    checked_at: datetime
    redis_ok: bool
    queues: list[OpsQueueDepth]
    platform: OpsPlatformCounts
    jobs: OpsJobsWindow
    jobs_by_status: list[OpsJobStatusCount]
    batches_by_status: list[OpsBatchStatusCount]
    recent_batches: list[OpsRecentBatch]
    stuck_batches: list[OpsStuckBatchResponse]
    recent_failed_jobs: list[OpsFailedJob]
