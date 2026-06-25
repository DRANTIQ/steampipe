#!/usr/bin/env python3
"""T-014: End-to-end smoke test — Stage 1 scan + compliance score.

Triggers a CIS scan on Stage 1, then polls compliance unified status (T-033)
until collection and evaluation complete.

Requires API_AUTH_REQUIRED=true on Stage 1 and compliance APIs (login first).

Exit 0 on success, 1 on timeout or failure.

Example (drantiq_platform):
  python scripts/smoke_e2e_scan.py \\
    --tenant-id 46e2c986-c8d3-44a6-8738-3c8b368fa8e8 \\
    --account-id 6a1a155e-243f-437b-a2c3-ba69be9258bc \\
    --email admin@drantiq.local \\
    --password password123
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api_auth import bearer_headers, login


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _poll_unified_scan_status(
    compliance_url: str,
    batch_id: str,
    *,
    auth_headers: dict[str, str],
    expected_controls: int,
    timeout: int,
    interval: int,
) -> dict[str, Any]:
    url = f"{compliance_url.rstrip('/')}/v1/scan-runs/{batch_id}/status"
    deadline = time.time() + timeout
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        try:
            status = _request("GET", url, headers=auth_headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"[unified] batch not visible yet batch={batch_id}")
                time.sleep(interval)
                continue
            raise
        last = status
        collection = status.get("collection") or {}
        compliance = status.get("compliance") or {}
        overall = status.get("overall_status")
        print(
            f"[unified] batch={batch_id} overall={overall} "
            f"collection={collection.get('completed_jobs', 0)}/{collection.get('total_jobs', 0)} "
            f"evaluated={compliance.get('evaluated_controls', 0)}/{compliance.get('total_controls', expected_controls)} "
            f"score={compliance.get('score_pct')}"
        )
        if overall == "completed":
            evaluated = compliance.get("evaluated_controls", 0)
            if evaluated >= expected_controls:
                return status
        if overall in ("failed", "partial"):
            return status
        time.sleep(interval)
    raise TimeoutError(
        f"Unified scan status for batch {batch_id} did not complete within {timeout}s "
        f"(last={json.dumps(last)})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E smoke: Stage 1 scan -> unified compliance status")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--stage1-url", default="http://localhost:8000")
    parser.add_argument("--compliance-url", default="http://localhost:8001")
    parser.add_argument("--framework-id", default="cis_aws_v6")
    parser.add_argument("--expected-controls", type=int, default=35)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--email", default=os.environ.get("SMOKE_EMAIL", "admin@drantiq.local"))
    parser.add_argument("--password", default=os.environ.get("SMOKE_PASSWORD", "password123"))
    parser.add_argument(
        "--skip-login",
        action="store_true",
        help="No Bearer token (only when API_AUTH_REQUIRED=false on both APIs)",
    )
    args = parser.parse_args()

    token: str | None = None
    if not args.skip_login:
        print(f"[auth] logging in as {args.email}...")
        session = login(args.stage1_url, args.email, args.password)
        token = session["access_token"]
        login_tenant = session.get("tenant_id")
        print(f"[auth] tenant_id={login_tenant} role={session.get('role')}")
        if login_tenant and login_tenant != args.tenant_id:
            print(
                f"smoke_e2e_scan FAILED: user tenant {login_tenant} != --tenant-id {args.tenant_id}. "
                "Use a user that belongs to the target tenant.",
                file=sys.stderr,
            )
            return 1

    headers = bearer_headers(token) if token else {"Content-Type": "application/json"}

    scan_url = f"{args.stage1_url.rstrip('/')}/api/v1/executions/scan"
    body = {
        "tenant_id": args.tenant_id,
        "account_id": args.account_id,
        "framework_id": args.framework_id,
        "category": "compliance",
        "triggered_by": "smoke_e2e_scan",
    }
    print("[stage1] triggering scan...")
    started = _request("POST", scan_url, headers=headers, body=body)
    batch_id = started["batch_id"]
    total_jobs = started.get("total_jobs", args.expected_controls)
    print(f"[stage1] batch_id={batch_id} total_jobs={total_jobs}")

    status = _poll_unified_scan_status(
        args.compliance_url,
        batch_id,
        auth_headers=headers,
        expected_controls=args.expected_controls,
        timeout=args.timeout,
        interval=args.poll_interval,
    )
    compliance = status.get("compliance") or {}
    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "overall_status": status.get("overall_status"),
                "collection": status.get("collection"),
                "evaluated_controls": compliance.get("evaluated_controls"),
                "pass_count": compliance.get("pass_count"),
                "fail_count": compliance.get("fail_count"),
                "score_pct": compliance.get("score_pct"),
                "score_weighted_pct": compliance.get("score_weighted_pct"),
                "drift_count": compliance.get("drift_count"),
                "catalog_total": compliance.get("catalog_total"),
                "manual_total": compliance.get("manual_total"),
            },
            indent=2,
        )
    )
    if status.get("overall_status") != "completed":
        print(f"smoke_e2e_scan FAILED: overall_status={status.get('overall_status')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as exc:
        print(f"smoke_e2e_scan FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
