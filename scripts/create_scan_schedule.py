#!/usr/bin/env python3
"""Create a recurring CIS/framework scan schedule (T-030).

Example (nightly 2am UTC for one account):
  python scripts/create_scan_schedule.py \\
    --tenant-id 5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47 \\
    --account-id e0e0075b-310d-4e37-9997-81626fe52580 \\
    --cron "0 2 * * *"
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a framework scan cron schedule")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--account-id", default=None, help="Optional; omit to scan all active accounts")
    parser.add_argument("--framework-id", default="cis_aws_v6")
    parser.add_argument("--category", default="compliance")
    parser.add_argument("--cron", dest="cron_expression", default="0 2 * * *")
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()

    body = {
        "tenant_id": args.tenant_id,
        "account_id": args.account_id,
        "framework_id": args.framework_id,
        "category": args.category,
        "cron_expression": args.cron_expression,
        "timezone": args.timezone,
        "enabled": True,
    }
    url = f"{args.api_url.rstrip('/')}/api/v1/schedules/scan"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            schedule = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode(), file=sys.stderr)
        return 1

    print(json.dumps(schedule, indent=2))
    print(f"\nSchedule {schedule['id']} next run: {schedule.get('next_run_at')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
