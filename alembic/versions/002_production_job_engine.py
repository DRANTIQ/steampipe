"""Production job engine: execution_batches, batch_id, content_hash, run_all, indexes.

Revision ID: 002
Revises: 001
Create Date: 2025-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. execution_batches (must exist before execution_jobs.batch_id FK)
    op.create_table(
        "execution_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", sa.String(36), sa.ForeignKey("query_schedules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("total_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_execution_batches_tenant_id", "execution_batches", ["tenant_id"], unique=False)
    op.create_index("ix_execution_batches_status", "execution_batches", ["status"], unique=False)
    op.create_index("ix_execution_batches_schedule_id", "execution_batches", ["schedule_id"], unique=False)

    # 2. execution_jobs.batch_id (nullable)
    op.add_column("execution_jobs", sa.Column("batch_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_execution_jobs_batch_id",
        "execution_jobs",
        "execution_batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_execution_jobs_batch_id", "execution_jobs", ["batch_id"], unique=False)
    op.create_index("ix_execution_jobs_status", "execution_jobs", ["status"], unique=False)
    op.create_index("ix_execution_jobs_tenant_id_status", "execution_jobs", ["tenant_id", "status"], unique=False)

    # 3. queries.content_hash
    op.add_column("queries", sa.Column("content_hash", sa.String(64), nullable=True))

    # 4. query_schedules.run_all, query_id nullable
    op.add_column("query_schedules", sa.Column("run_all", sa.Boolean(), nullable=False, server_default="false"))
    op.alter_column(
        "query_schedules",
        "query_id",
        existing_type=sa.String(36),
        nullable=True,
    )

    # 5. query_schedules index for scheduler (enabled, next_run_at)
    op.create_index(
        "ix_query_schedules_enabled_next_run_at",
        "query_schedules",
        ["enabled", "next_run_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_query_schedules_enabled_next_run_at", table_name="query_schedules")
    op.alter_column(
        "query_schedules",
        "query_id",
        existing_type=sa.String(36),
        nullable=False,
    )
    op.drop_column("query_schedules", "run_all")
    op.drop_column("queries", "content_hash")
    op.drop_index("ix_execution_jobs_tenant_id_status", table_name="execution_jobs")
    op.drop_index("ix_execution_jobs_status", table_name="execution_jobs")
    op.drop_index("ix_execution_jobs_batch_id", table_name="execution_jobs")
    op.drop_constraint("fk_execution_jobs_batch_id", "execution_jobs", type_="foreignkey")
    op.drop_column("execution_jobs", "batch_id")
    op.drop_index("ix_execution_batches_schedule_id", table_name="execution_batches")
    op.drop_index("ix_execution_batches_status", table_name="execution_batches")
    op.drop_index("ix_execution_batches_tenant_id", table_name="execution_batches")
    op.drop_table("execution_batches")
