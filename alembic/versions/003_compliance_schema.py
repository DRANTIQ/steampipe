"""Compliance schema and tables: controls, snapshots, evaluation_runs, execution_snapshot_rows, control_results, etc.

Revision ID: 003
Revises: 002
Create Date: 2025-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS compliance")

    # Core catalogs
    op.create_table(
        "controls",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("control_id", sa.Text(), nullable=False),
        sa.Column("framework_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        schema="compliance",
    )
    op.create_index("ix_compliance_controls_framework_id", "controls", ["framework_id"], schema="compliance")
    op.create_unique_constraint("uq_compliance_controls_framework_control", "controls", ["framework_id", "control_id"], schema="compliance")

    op.create_table(
        "framework_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("framework_id", sa.Text(), nullable=False),
        sa.Column("version_name", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("hash", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="compliance",
    )
    op.create_unique_constraint("uq_compliance_framework_versions", "framework_versions", ["framework_id", "version_name"], schema="compliance")

    op.create_table(
        "rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("framework_id", sa.Text(), nullable=False),
        sa.Column("version_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="compliance",
    )
    op.create_unique_constraint("uq_compliance_rule_versions", "rule_versions", ["framework_id", "version_name"], schema="compliance")

    # Snapshots & runs
    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sources", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("s3_prefix", sa.Text(), nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_job_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="compliance",
    )
    op.create_index("ix_compliance_snapshots_tenant_account", "snapshots", ["tenant_id", "account_id"], schema="compliance")

    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("regions", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("framework_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rule_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("run_hash", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["framework_version_id"], ["compliance.framework_versions.id"], name="fk_eval_run_framework_version"),
        sa.ForeignKeyConstraint(["rule_version_id"], ["compliance.rule_versions.id"], name="fk_eval_run_rule_version"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["compliance.snapshots.id"], name="fk_eval_run_snapshot"),
        schema="compliance",
    )
    op.create_index("ix_compliance_evaluation_runs_snapshot", "evaluation_runs", ["snapshot_id"], schema="compliance")
    op.create_unique_constraint("uq_compliance_evaluation_runs_idempotency", "evaluation_runs", ["idempotency_key"], schema="compliance")

    # Extract storage
    op.create_table(
        "execution_snapshot_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("record_type", sa.Text(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("natural_key", sa.Text(), nullable=True),
        sa.Column("record_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["compliance.snapshots.id"], name="fk_snapshot_rows_snapshot"),
        schema="compliance",
    )
    op.create_index("ix_compliance_snapshot_rows_snapshot", "execution_snapshot_rows", ["snapshot_id"], schema="compliance")
    op.create_index("ix_compliance_snapshot_rows_tenant_time", "execution_snapshot_rows", ["tenant_id", "created_at"], schema="compliance")
    op.create_index("ix_compliance_snapshot_rows_source_type", "execution_snapshot_rows", ["snapshot_id", "source", "record_type"], schema="compliance")
    op.create_unique_constraint("uq_compliance_snapshot_rows_hash", "execution_snapshot_rows", ["snapshot_id", "record_hash"], schema="compliance")
    op.execute("CREATE INDEX ix_compliance_snapshot_rows_gin ON compliance.execution_snapshot_rows USING GIN (payload)")

    # Evaluation output
    op.create_table(
        "control_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", sa.Text(), nullable=False),
        sa.Column("control_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=True),
        sa.Column("score_delta", sa.Numeric(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("rule_definition_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("prev_result_hash", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["compliance.evaluation_runs.id"], name="fk_control_results_run"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["compliance.snapshots.id"], name="fk_control_results_snapshot"),
        schema="compliance",
    )
    op.create_index("ix_compliance_control_results_run", "control_results", ["evaluation_run_id"], schema="compliance")
    op.create_index("ix_compliance_control_results_tenant", "control_results", ["tenant_id"], schema="compliance")
    op.create_unique_constraint("uq_compliance_control_results_run_control", "control_results", ["evaluation_run_id", "control_id"], schema="compliance")

    op.create_table(
        "control_evidence_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("evidence_locator", sa.Text(), nullable=True),
        sa.Column("evidence_hash", sa.String(64), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("payload_excerpt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["control_result_id"], ["compliance.control_results.id"], ondelete="CASCADE", name="fk_evidence_control_result"),
        schema="compliance",
    )
    op.create_index("ix_compliance_evidence_control", "control_evidence_resources", ["control_result_id"], schema="compliance")
    op.create_index("ix_compliance_evidence_resource", "control_evidence_resources", ["resource_type", "resource_id"], schema="compliance")

    # Latest cache & summaries
    op.create_table(
        "control_state",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", sa.Text(), nullable=False),
        sa.Column("control_id", sa.Text(), nullable=False),
        sa.Column("latest_control_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("latest_status", sa.Text(), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "account_id", "framework_id", "control_id"),
        sa.ForeignKeyConstraint(["latest_control_result_id"], ["compliance.control_results.id"], name="fk_control_state_result"),
        schema="compliance",
    )

    op.create_table(
        "compliance_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework_id", sa.Text(), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pass_count", sa.Integer(), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        sa.Column("unknown_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_total", sa.Numeric(), nullable=True),
        sa.Column("severity_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["compliance.evaluation_runs.id"], name="fk_summary_run"),
        schema="compliance",
    )

    # Jobs & metrics
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="compliance",
    )

    op.create_table(
        "control_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("control_id", sa.Text(), nullable=False),
        sa.Column("query_time_ms", sa.Integer(), nullable=True),
        sa.Column("rows_scanned", sa.Integer(), nullable=True),
        sa.Column("evidence_count", sa.Integer(), nullable=True),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="compliance",
    )

    # RLS: when app.tenant_id is set (by API), filter by it; when not set (e.g. backend), allow (for workers).
    rls_using = "((current_setting('app.tenant_id', true) IS NULL) OR (tenant_id = current_setting('app.tenant_id', true)::uuid))"
    for table in [
        "snapshots", "evaluation_runs", "execution_snapshot_rows", "control_results",
        "control_evidence_resources", "control_state", "compliance_summary", "jobs", "control_metrics"
    ]:
        op.execute(f'ALTER TABLE compliance."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON compliance."{table}"
               USING {rls_using}'''
        )


def downgrade() -> None:
    for table in [
        "control_metrics", "jobs", "compliance_summary", "control_state",
        "control_evidence_resources", "control_results", "execution_snapshot_rows",
        "evaluation_runs", "snapshots", "rule_versions", "framework_versions", "controls"
    ]:
        op.drop_table(table, schema="compliance")
    op.execute("DROP SCHEMA IF EXISTS compliance")
