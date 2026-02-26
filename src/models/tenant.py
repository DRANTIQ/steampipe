from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_type: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    max_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_executions_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    users = relationship("User", back_populates="tenant")
    api_keys = relationship("APIKey", back_populates="tenant")
    cloud_accounts = relationship("CloudAccount", back_populates="tenant")
    query_schedules = relationship("QuerySchedule", back_populates="tenant")
    execution_jobs = relationship("ExecutionJob", back_populates="tenant")
    execution_batches = relationship("ExecutionBatch", back_populates="tenant")
