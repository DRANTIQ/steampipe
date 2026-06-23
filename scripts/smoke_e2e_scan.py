#!/usr/bin/env python3
"""T-014: End-to-end smoke test — Stage 1 scan + compliance score.

Triggers a CIS scan, waits for Stage 1 batch completion, then polls compliance
until the scan run is completed with all controls evaluated.

Exit 0 on success, 1 on timeout or failure.

Example:
  python scripts/smoke_e2e_scan.py \\
    --tenant-id 5b12b902-d1fc-4aec-b0fb-f2d7e8af4b47 \\
    --account-id e0e0075b-310d-4e37-9997-81626fe52580
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


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


def _poll_stage1_batch(
    base_url: str,
    batch_id: str,
    *,
    timeout: int,
    interval: int,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v1/executions/batches/{batch_id}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        batch = _request("GET", url)
        status = batch.get("status")
        completed = batch.get("completed_jobs", 0)
        failed = batch.get("failed_jobs", 0)
        total = batch.get("total_jobs", 0)
        print(f"[stage1] batch={batch_id} status={status} done={completed}/{total} failed={failed}")
        if status in ("completed", "failed", "partial"):
            if failed > 0:
                print(f"[stage1] WARNING: {failed} job(s) failed", file=sys.stderr)
            return batch
        time.sleep(interval)
    raise TimeoutError(f"Stage 1 batch {batch_id} did not finish within {timeout}s")


def _poll_compliance_scan(
    base_url: str,
    batch_id: str,
    tenant_id: str,
    *,
    expected_controls: int,
    timeout: int,
    interval: int,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/scan-runs/{batch_id}"
    headers = {"X-Tenant-Id": tenant_id}
    deadline = time.time() + timeout
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        try:
            scan = _request("GET", url, headers=headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                print(f"[compliance] scan not created yet for batch={batch_id}")
                time.sleep(interval)
                continue
            raise
        last = scan
        evaluated = scan.get("evaluated_controls", 0)
        total = scan.get("total_controls", expected_controls)
        status = scan.get("status")
        print(
            f"[compliance] batch={batch_id} status={status} "
            f"evaluated={evaluated}/{total} score={scan.get('score_pct')}"
        )
        if status == "completed" and evaluated >= expected_controls:
            return scan
        time.sleep(interval)
    raise TimeoutError(
        f"Compliance scan for batch {batch_id} did not complete within {timeout}s "
        f"(last={json.dumps(last)})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E smoke: Stage 1 scan → compliance score")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--stage1-url", default="http://localhost:8000")
    parser.add_argument("--compliance-url", default="http://localhost:8001")
    parser.add_argument("--framework-id", default="cis_aws_v6")
    parser.add_argument("--expected-controls", type=int, default=35)
    parser.add_argument("--stage1-timeout", type=int, default=900)
    parser.add_argument("--compliance-timeout", type=int, default=600)
    parser.add_argument("--poll-interval", type=int, default=10)
    args = parser.parse_args()

    scan_url = f"{args.stage1_url.rstrip('/')}/api/v1/executions/scan"
    body = {
        "tenant_id": args.tenant_id,
        "account_id": args.account_id,
        "framework_id": args.framework_id,
        "category": "compliance",
        "triggered_by": "smoke_e2e_scan",
    }
    print("[stage1] triggering scan...")
    started = _request("POST", scan_url, body=body)
    batch_id = started["batch_id"]
    total_jobs = started.get("total_jobs", args.expected_controls)
    print(f"[stage1] batch_id={batch_id} total_jobs={total_jobs}")

    _poll_stage1_batch(
        args.stage1_url,
        batch_id,
        timeout=args.stage1_timeout,
        interval=args.poll_interval,
    )

    scan = _poll_compliance_scan(
        args.compliance_url,
        batch_id,
        args.tenant_id,
        expected_controls=args.expected_controls,
        timeout=args.compliance_timeout,
        interval=args.poll_interval,
    )
    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "status": scan.get("status"),
                "evaluated_controls": scan.get("evaluated_controls"),
                "pass_count": scan.get("pass_count"),
                "fail_count": scan.get("fail_count"),
                "score_pct": scan.get("score_pct"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"smoke_e2e_scan FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
