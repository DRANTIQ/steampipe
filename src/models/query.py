from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin
from src.models.enums import CloudProvider


class Query(Base, TimestampMixin):
    __tablename__ = "queries"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_query_name_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0")
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    plugin: Mapped[str] = mapped_column(String(64), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="single_account")
    output_format: Mapped[str] = mapped_column(String(16), nullable=False, default="json")
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    execution_jobs = relationship("ExecutionJob", back_populates="query")
    schedules = relationship("QuerySchedule", back_populates="query")
