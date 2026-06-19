"""Pydantic schemas for API."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID
from typing import Any

from pydantic import BaseModel, Field


class EvaluationRunCreate(BaseModel):
    account_id: UUID
    snapshot_id: UUID | None = None
    s3_prefix: str | None = None
    framework_id: str = "cis_aws_v6"
    rule_version: str | None = None


class ControlResultResponse(BaseModel):
    id: UUID
    control_id: str
    status: str
    severity: str | None
    message: str | None
    evaluated_at: datetime | None
    details: dict[str, Any] | None

    model_config = {"from_attributes": True}


class ControlStatusLatest(BaseModel):
    control_id: str
    latest_status: str
    last_evaluated_at: datetime
    framework_id: str


class SimulateRequest(BaseModel):
    snapshot_id: UUID
    rule_version_id: UUID | None = None
    proposed_rules: list[dict[str, Any]] | None = None


class IngestSnapshotRequest(BaseModel):
    """Trigger snapshot JSON → Postgres only (no evaluation)."""
    snapshot_path: str = Field(..., description="Full path: s3://bucket/key or local file path")
    account_id: UUID
    execution_job_id: str | None = Field(None, description="Optional; from execution platform for traceability")
