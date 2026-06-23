"""Per-control rule definitions and bronze-pinned rule metadata on snapshots.

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rule_versions",
        sa.Column(
            "definitions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        schema="compliance",
    )
    op.add_column(
        "snapshots",
        sa.Column("rule_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="compliance",
    )


def downgrade() -> None:
    op.drop_column("snapshots", "rule_metadata", schema="compliance")
    op.drop_column("rule_versions", "definitions", schema="compliance")
