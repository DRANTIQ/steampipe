#!/usr/bin/env python3
"""Seed dummy data for local dev and tests. Never run against production."""
from __future__ import annotations

import os
import sys
from uuid import uuid4

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.models import (
    Tenant,
    User,
    CloudAccount,
    Query,
    QuerySchedule,
)
from src.models.enums import UserRole
from src.scheduler.cron_scheduler import compute_next_run
from src.services.database import get_db_session_factory


def seed(session: Session) -> None:
    if session.query(Tenant).count() > 0:
        print("Data already present; skip seeding.")
        return

    # Tenants
    tenants = [
        Tenant(
            id=str(uuid4()),
            name="acme-free",
            description="Free tier",
            plan_type="free",
            max_accounts=2,
            max_queries=5,
            max_executions_per_day=20,
        ),
        Tenant(
            id=str(uuid4()),
            name="acme-pro",
            description="Pro tier",
            plan_type="pro",
            max_accounts=10,
            max_queries=50,
            max_executions_per_day=500,
        ),
        Tenant(
            id=str(uuid4()),
            name="acme-enterprise",
            description="Enterprise",
            plan_type="enterprise",
            max_accounts=100,
            max_queries=500,
            max_executions_per_day=10000,
        ),
    ]
    for t in tenants:
        session.add(t)
    session.flush()

    # Users per tenant (password: password123)
    hashed = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    for t in tenants:
        for email, role in [
            (f"admin-{t.name}@example.com", UserRole.tenant_admin.value),
            (f"user-{t.name}@example.com", UserRole.tenant_user.value),
        ]:
            session.add(User(
                id=str(uuid4()),
                tenant_id=t.id,
                email=email,
                username=email.split("@")[0],
                hashed_password=hashed,
                role=role,
            ))
    session.flush()

    # Cloud accounts per tenant
    for t in tenants:
        for provider, account_id, region, name in [
            ("aws", "123456789012", "us-east-1", "AWS Main"),
            ("azure", "sub-id-1", "eastus", "Azure Sub"),
            ("gcp", "project-1", "us-central1", "GCP Project"),
        ]:
            session.add(CloudAccount(
                id=str(uuid4()),
                tenant_id=t.id,
                provider=provider,
                account_id=account_id,
                region=region,
                name=name,
            ))
    session.flush()

    # Queries (shared; no tenant_id on Query)
    queries = [
        Query(
            id=str(uuid4()),
            name="list_ec2_instances",
            version="1.0",
            provider="aws",
            plugin="aws",
            query_text="select instance_id, instance_state from aws_ec2_instance limit 5",
            execution_mode="single_account",
            output_format="json",
            schedule_enabled=False,
        ),
        Query(
            id=str(uuid4()),
            name="list_azure_vms",
            version="1.0",
            provider="azure",
            plugin="azure",
            query_text="select name, power_state from azure_compute_virtual_machine limit 5",
            execution_mode="single_account",
            output_format="json",
            schedule_enabled=False,
        ),
    ]
    for q in queries:
        session.add(q)
    session.flush()

    # One schedule: first tenant, first query
    session.add(QuerySchedule(
        id=str(uuid4()),
        tenant_id=tenants[0].id,
        query_id=queries[0].id,
        cron_expression="0 * * * *",
        timezone="UTC",
        enabled=True,
        next_run_at=compute_next_run("0 * * * *", "UTC"),
    ))

    session.commit()
    print("Dummy data seeded: tenants, users, cloud accounts, queries, 1 schedule.")


def _session_factory_for_url(url: str):
    """Create a session factory for the given URL (e.g. local DB)."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def main() -> None:
    get_settings()
    # Prefer SEED_DATABASE_URL for local seeding when .env points at a remote DB
    seed_url = os.environ.get("SEED_DATABASE_URL")
    if seed_url:
        factory = _session_factory_for_url(seed_url)
    else:
        factory = get_db_session_factory()
    with factory() as session:
        seed(session)


if __name__ == "__main__":
    main()
