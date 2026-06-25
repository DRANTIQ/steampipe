#!/usr/bin/env python3
"""Create a login user for a tenant (T-022 dev/setup).

Example:
  python scripts/create_tenant_user.py \\
    --tenant-id 5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47 \\
    --email admin@drantiq.local \\
    --password password123 \\
    --role tenant_admin
"""
from __future__ import annotations

import argparse
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Tenant, User
from src.models.enums import UserRole
from src.services.auth import hash_password
from src.services.database import get_db_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="Create tenant user for JWT login")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="tenant_admin", choices=[r.value for r in UserRole if r != UserRole.super_admin])
    parser.add_argument("--username", default=None)
    args = parser.parse_args()

    factory = get_db_session_factory()
    with factory() as session:
        tenant = session.get(Tenant, args.tenant_id)
        if not tenant:
            print(f"Tenant not found: {args.tenant_id}", file=sys.stderr)
            return 1
        email = args.email.lower()
        existing = session.query(User).filter(User.email == email).first()
        if existing:
            existing.hashed_password = hash_password(args.password)
            existing.role = args.role
            existing.active = True
            print(f"Updated user {email} (tenant {tenant.name})")
        else:
            session.add(
                User(
                    id=str(uuid4()),
                    tenant_id=args.tenant_id,
                    email=email,
                    username=args.username or email.split("@")[0],
                    hashed_password=hash_password(args.password),
                    role=args.role,
                    active=True,
                )
            )
            print(f"Created user {email} (tenant {tenant.name})")
        session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
