"""SQLAlchemy models for compliance schema."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ComplianceBase(DeclarativeBase):
    pass


class Snapshot(ComplianceBase):
    __tablename__ = "snapshots"
    __table_args__ = {"schema": "compliance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sources: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    s3_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    execution_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)


class ExecutionSnapshotRow(ComplianceBase):
    __tablename__ = "execution_snapshot_rows"
    __table_args__ = (UniqueConstraint("snapshot_id", "record_hash", name="uq_compliance_snapshot_rows_hash"), {"schema": "compliance"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.snapshots.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    record_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    natural_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)


class FrameworkVersion(ComplianceBase):
    __tablename__ = "framework_versions"
    __table_args__ = {"schema": "compliance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    framework_id: Mapped[str] = mapped_column(Text, nullable=False)
    version_name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)  # aws | azure | gcp
    category: Mapped[str | None] = mapped_column(Text, nullable=True)  # compliance | cost_optimization | ...
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RuleVersion(ComplianceBase):
    __tablename__ = "rule_versions"
    __table_args__ = {"schema": "compliance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    framework_id: Mapped[str] = mapped_column(Text, nullable=False)
    version_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvaluationRun(ComplianceBase):
    __tablename__ = "evaluation_runs"
    __table_args__ = {"schema": "compliance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    regions: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    framework_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.framework_versions.id"), nullable=True)
    rule_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.rule_versions.id"), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)
    snapshot_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.snapshots.id"), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ControlResult(ComplianceBase):
    __tablename__ = "control_results"
    __table_args__ = (UniqueConstraint("evaluation_run_id", "control_id", name="uq_compliance_control_results_run_control"), {"schema": "compliance"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    evaluation_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.evaluation_runs.id"), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.snapshots.id"), nullable=False)
    framework_id: Mapped[str] = mapped_column(Text, nullable=False)
    control_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_delta: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ControlEvidenceResource(ComplianceBase):
    __tablename__ = "control_evidence_resources"
    __table_args__ = {"schema": "compliance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    control_result_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.control_results.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_excerpt: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)


class ControlState(ComplianceBase):
    __tablename__ = "control_state"
    __table_args__ = {"schema": "compliance"}

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    framework_id: Mapped[str] = mapped_column(Text, primary_key=True)
    control_id: Mapped[str] = mapped_column(Text, primary_key=True)
    latest_control_result_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.control_results.id"), nullable=True)
    latest_status: Mapped[str] = mapped_column(Text, nullable=False)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_snapshot_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)


class ComplianceSummary(ComplianceBase):
    __tablename__ = "compliance_summary"
    __table_args__ = {"schema": "compliance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    framework_id: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("compliance.evaluation_runs.id"), nullable=True)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    score_total: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    severity_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=True)


class Control(ComplianceBase):
    __tablename__ = "controls"
    __table_args__ = {"schema": "compliance"}

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    control_id: Mapped[str] = mapped_column(Text, nullable=False)
    framework_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)  # aws | azure | gcp
    category: Mapped[str | None] = mapped_column(Text, nullable=True)  # compliance | cost_optimization | ...
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    references: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
