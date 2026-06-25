#!/usr/bin/env python3
"""Create or update the platform tenant that scans using AWS creds from .env (no assume-role).

Use this for Drantiq's own AWS account: workers read AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
from the environment. Do not set role_arn on the cloud account unless you intend cross-account assume.

Example:
  python scripts/setup_platform_tenant.py
  python scripts/setup_platform_tenant.py --tenant-name drantiq_platform --discover-aws-account

Prints tenant_id and account_id for cloud-compliance-ui / admin UI .env files.
"""
from __future__ import annotations

import argparse
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_settings
from src.models import CloudAccount, Tenant, User
from src.models.enums import UserRole
from src.services.auth import hash_password
from src.services.database import get_db_session_factory


def _discover_aws_account_id() -> str:
    settings = get_settings()
    if not (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY):
        raise SystemExit(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in .env to discover account ID"
        )
    import boto3

    kwargs: dict = {
        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
        "region_name": settings.S3_REGION or "us-east-1",
    }
    if settings.AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = settings.AWS_SESSION_TOKEN
    identity = boto3.client("sts", **kwargs).get_caller_identity()
    account_id = identity.get("Account")
    if not account_id:
        raise SystemExit("STS GetCallerIdentity did not return Account")
    print(f"Discovered AWS account: {account_id} ({identity.get('Arn', '')})")
    return str(account_id)


def _upsert_user(
    session,
    *,
    tenant_id: str,
    email: str,
    password: str,
    role: str,
) -> None:
    email = email.lower()
    user = session.query(User).filter(User.email == email).first()
    hashed = hash_password(password)
    if user:
        user.tenant_id = tenant_id
        user.hashed_password = hashed
        user.role = role
        user.active = True
        action = "Updated"
    else:
        session.add(
            User(
                id=str(uuid4()),
                tenant_id=tenant_id,
                email=email,
                username=email.split("@")[0],
                hashed_password=hashed,
                role=role,
                active=True,
            )
        )
        action = "Created"
    print(f"{action} user {email} ({role})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Platform tenant using .env AWS credentials")
    parser.add_argument("--tenant-name", default="drantiq_platform", help="Unique tenant slug/name")
    parser.add_argument(
        "--tenant-description",
        default="Platform tenant — scans own AWS account via worker .env credentials",
    )
    parser.add_argument("--aws-account-id", default=None, help="12-digit AWS account; default: STS discover")
    parser.add_argument("--discover-aws-account", action="store_true", help="Always call STS (default if --aws-account-id omitted)")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--account-display-name", default="Platform AWS (env creds)")
    parser.add_argument("--super-admin-email", default="ops@drantiq.local")
    parser.add_argument("--tenant-admin-email", default="admin@drantiq.local")
    parser.add_argument("--password", default="password123")
    parser.add_argument("--plan-type", default="enterprise")
    parser.add_argument("--max-executions-per-day", type=int, default=10000)
    args = parser.parse_args()

    aws_account_id = args.aws_account_id
    if not aws_account_id:
        aws_account_id = _discover_aws_account_id()

    factory = get_db_session_factory()
    with factory() as session:
        tenant = session.query(Tenant).filter(Tenant.name == args.tenant_name, Tenant.deleted_at.is_(None)).first()
        if tenant:
            tenant.description = args.tenant_description
            tenant.plan_type = args.plan_type
            tenant.max_executions_per_day = args.max_executions_per_day
            tenant.active = True
            print(f"Using existing tenant: {tenant.name} ({tenant.id})")
        else:
            tenant = Tenant(
                id=str(uuid4()),
                name=args.tenant_name,
                description=args.tenant_description,
                plan_type=args.plan_type,
                max_accounts=50,
                max_queries=500,
                max_executions_per_day=args.max_executions_per_day,
                active=True,
            )
            session.add(tenant)
            session.flush()
            print(f"Created tenant: {tenant.name} ({tenant.id})")

        account = (
            session.query(CloudAccount)
            .filter(
                CloudAccount.tenant_id == tenant.id,
                CloudAccount.provider == "aws",
                CloudAccount.account_id == aws_account_id,
                CloudAccount.deleted_at.is_(None),
            )
            .first()
        )
        platform_meta = {
            "credential_mode": "platform_env",
            "note": "No role_arn — worker uses AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY from .env",
        }
        if account:
            account.name = args.account_display_name
            account.region = args.region
            account.active = True
            account.secret_arn = None
            account.extra_metadata = platform_meta
            print(f"Updated cloud account: {account.id} (aws/{aws_account_id})")
        else:
            account = CloudAccount(
                id=str(uuid4()),
                tenant_id=tenant.id,
                provider="aws",
                account_id=aws_account_id,
                region=args.region,
                name=args.account_display_name,
                secret_arn=None,
                extra_metadata=platform_meta,
                active=True,
            )
            session.add(account)
            session.flush()
            print(f"Created cloud account: {account.id} (aws/{aws_account_id})")

        _upsert_user(
            session,
            tenant_id=tenant.id,
            email=args.super_admin_email,
            password=args.password,
            role=UserRole.super_admin.value,
        )
        _upsert_user(
            session,
            tenant_id=tenant.id,
            email=args.tenant_admin_email,
            password=args.password,
            role=UserRole.tenant_admin.value,
        )

        session.commit()

        print("\n--- Add to UI .env.local ---")
        print(f"VITE_TENANT_ID={tenant.id}")
        print(f"VITE_ACCOUNT_ID={account.id}")
        print("\n--- Login ---")
        print(f"Admin UI (:5174):  {args.super_admin_email} / {args.password}")
        print(f"Client UI (:5173): {args.tenant_admin_email} / {args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
