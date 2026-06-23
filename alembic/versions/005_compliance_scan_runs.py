"""Compliance scan_runs + snapshot lineage columns.

Revision ID: 005
Revises: 004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("framework_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("total_controls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluated_controls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pass_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unknown_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_pct", sa.Numeric(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="compliance",
    )
    op.create_index("ix_compliance_scan_runs_tenant", "scan_runs", ["tenant_id"], schema="compliance")
    op.create_index("ix_compliance_scan_runs_batch", "scan_runs", ["batch_id"], schema="compliance")
    op.create_unique_constraint(
        "uq_compliance_scan_runs_batch",
        "scan_runs",
        ["tenant_id", "batch_id"],
        schema="compliance",
    )

    op.add_column("snapshots", sa.Column("batch_id", sa.String(36), nullable=True), schema="compliance")
    op.add_column("snapshots", sa.Column("framework_id", sa.Text(), nullable=True), schema="compliance")
    op.add_column("snapshots", sa.Column("control_ref", sa.Text(), nullable=True), schema="compliance")
    op.add_column("snapshots", sa.Column("control_id", sa.Text(), nullable=True), schema="compliance")
    op.add_column("snapshots", sa.Column("query_id", sa.String(36), nullable=True), schema="compliance")
    op.add_column("snapshots", sa.Column("query_name", sa.Text(), nullable=True), schema="compliance")
    op.add_column(
        "snapshots",
        sa.Column("scan_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="compliance",
    )
    op.create_foreign_key(
        "fk_compliance_snapshots_scan_run",
        "snapshots",
        "scan_runs",
        ["scan_run_id"],
        ["id"],
        source_schema="compliance",
        referent_schema="compliance",
    )
    op.create_index("ix_compliance_snapshots_batch", "snapshots", ["batch_id"], schema="compliance")
    op.create_index("ix_compliance_snapshots_exec_job", "snapshots", ["execution_job_id"], schema="compliance")

    op.add_column(
        "evaluation_runs",
        sa.Column("scan_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="compliance",
    )
    op.add_column("evaluation_runs", sa.Column("framework_id", sa.Text(), nullable=True), schema="compliance")
    op.add_column("evaluation_runs", sa.Column("control_ref", sa.Text(), nullable=True), schema="compliance")
    op.create_foreign_key(
        "fk_compliance_evaluation_runs_scan_run",
        "evaluation_runs",
        "scan_runs",
        ["scan_run_id"],
        ["id"],
        source_schema="compliance",
        referent_schema="compliance",
    )

    op.add_column(
        "compliance_summary",
        sa.Column("scan_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="compliance",
    )
    op.create_foreign_key(
        "fk_compliance_summary_scan_run",
        "compliance_summary",
        "scan_runs",
        ["scan_run_id"],
        ["id"],
        source_schema="compliance",
        referent_schema="compliance",
    )


def downgrade() -> None:
    op.drop_constraint("fk_compliance_summary_scan_run", "compliance_summary", schema="compliance", type_="foreignkey")
    op.drop_column("compliance_summary", "scan_run_id", schema="compliance")

    op.drop_constraint(
        "fk_compliance_evaluation_runs_scan_run", "evaluation_runs", schema="compliance", type_="foreignkey"
    )
    op.drop_column("evaluation_runs", "control_ref", schema="compliance")
    op.drop_column("evaluation_runs", "framework_id", schema="compliance")
    op.drop_column("evaluation_runs", "scan_run_id", schema="compliance")

    op.drop_constraint("fk_compliance_snapshots_scan_run", "snapshots", schema="compliance", type_="foreignkey")
    op.drop_index("ix_compliance_snapshots_exec_job", table_name="snapshots", schema="compliance")
    op.drop_index("ix_compliance_snapshots_batch", table_name="snapshots", schema="compliance")
    op.drop_column("snapshots", "scan_run_id", schema="compliance")
    op.drop_column("snapshots", "query_name", schema="compliance")
    op.drop_column("snapshots", "query_id", schema="compliance")
    op.drop_column("snapshots", "control_id", schema="compliance")
    op.drop_column("snapshots", "control_ref", schema="compliance")
    op.drop_column("snapshots", "framework_id", schema="compliance")
    op.drop_column("snapshots", "batch_id", schema="compliance")

    op.drop_constraint("uq_compliance_scan_runs_batch", "scan_runs", schema="compliance", type_="unique")
    op.drop_index("ix_compliance_scan_runs_batch", table_name="scan_runs", schema="compliance")
    op.drop_index("ix_compliance_scan_runs_tenant", table_name="scan_runs", schema="compliance")
    op.drop_table("scan_runs", schema="compliance")
