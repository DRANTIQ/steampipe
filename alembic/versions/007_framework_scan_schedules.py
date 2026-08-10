"""Framework scan schedules on query_schedules (T-030).

Revision ID: 007
Revises: 002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "query_schedules",
        sa.Column("schedule_kind", sa.String(32), nullable=False, server_default="query"),
    )
    op.add_column(
        "query_schedules",
        sa.Column("framework_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "query_schedules",
        sa.Column("category", sa.Text(), nullable=True),
    )
    op.add_column(
        "query_schedules",
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.alter_column("query_schedules", "query_id", existing_type=sa.String(36), nullable=True)


def downgrade() -> None:
    op.alter_column("query_schedules", "query_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("query_schedules", "account_id")
    op.drop_column("query_schedules", "category")
    op.drop_column("query_schedules", "framework_id")
    op.drop_column("query_schedules", "schedule_kind")
