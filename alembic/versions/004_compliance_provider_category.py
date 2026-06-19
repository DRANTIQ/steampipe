"""Add provider and category to framework_versions and controls for multi-provider and cost/compliance.

Revision ID: 004
Revises: 003
Create Date: 2025-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("framework_versions", sa.Column("provider", sa.Text(), nullable=True), schema="compliance")
    op.add_column("framework_versions", sa.Column("category", sa.Text(), nullable=True), schema="compliance")
    op.add_column("controls", sa.Column("provider", sa.Text(), nullable=True), schema="compliance")
    op.add_column("controls", sa.Column("category", sa.Text(), nullable=True), schema="compliance")
    op.create_index("ix_compliance_framework_versions_provider", "framework_versions", ["provider"], schema="compliance")
    op.create_index("ix_compliance_framework_versions_category", "framework_versions", ["category"], schema="compliance")
    op.create_index("ix_compliance_controls_provider", "controls", ["provider"], schema="compliance")
    op.create_index("ix_compliance_controls_category", "controls", ["category"], schema="compliance")


def downgrade() -> None:
    op.drop_index("ix_compliance_controls_category", "controls", schema="compliance")
    op.drop_index("ix_compliance_controls_provider", "controls", schema="compliance")
    op.drop_index("ix_compliance_framework_versions_category", "framework_versions", schema="compliance")
    op.drop_index("ix_compliance_framework_versions_provider", "framework_versions", schema="compliance")
    op.drop_column("controls", "category", schema="compliance")
    op.drop_column("controls", "provider", schema="compliance")
    op.drop_column("framework_versions", "category", schema="compliance")
    op.drop_column("framework_versions", "provider", schema="compliance")
