#!/usr/bin/env python3
"""Enrich data/queries.json compliance entries: framework_id, natural_key, CIS v6 alignment."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

QUERIES_JSON = PROJECT_ROOT / "data" / "queries.json"
CIS_QUERIES_JSON = PROJECT_ROOT / "cloud-compliance-engine" / "queries" / "cis_v6_queries.json"

FRAMEWORK_ID = "cis_aws_v6"
FRAMEWORK_TITLE = "CIS AWS Foundations Benchmark v6.0.0"


def infer_natural_key(required_columns: list[str] | None) -> str:
    if not required_columns:
        return "id"
    priority = (
        "name",
        "db_instance_identifier",
        "instance_id",
        "account_id",
        "user_name",
        "network_acl_id",
        "group_id",
        "access_key_id",
        "file_system_id",
        "vpc_id",
        "region",
    )
    for key in priority:
        if key in required_columns:
            return key
    return required_columns[0]

# Legacy pre-cis_* queries: map to control metadata (not in cis_v6_queries.json)
LEGACY_CONTROL_META: dict[str, dict] = {
    "s3_buckets_versioning_disabled": {
        "control_ref": "s3-versioning",
        "control_id": "2.1.1",
    },
    "s3_buckets_default_encryption_disabled": {
        "control_ref": "s3-encryption",
        "control_id": "2.1.2",
    },
    "s3_buckets_public_policy": {
        "control_ref": "s3-public-policy",
        "control_id": "3.1.2",
    },
    "ec2_detailed_monitoring_disabled": {
        "control_ref": "ec2-detailed-monitoring",
        "control_id": "5.1",
    },
    "rds_iam_auth_disabled": {
        "control_ref": "rds-iam-auth",
        "control_id": "3.2.4",
    },
    "iam_access_keys_inactive": {
        "control_ref": "iam-inactive-keys",
        "control_id": "2.10",
    },
}


def cis_by_name(cis_data: dict) -> dict[str, dict]:
    return {q["name"]: q for q in cis_data.get("queries", [])}


def enrich_extra_metadata(entry: dict, cis: dict[str, dict]) -> dict:
    meta = dict(entry.get("extra_metadata") or {})
    name = entry["name"]

    if meta.get("category") != "compliance":
        return meta

    if name in cis:
        src = cis[name]
        meta.setdefault("framework", FRAMEWORK_TITLE)
        meta["framework_id"] = FRAMEWORK_ID
        meta["control_id"] = src["control_id"]
        meta["control_ref"] = src["control_ref"]
        meta["required_columns"] = src["required_columns"]
        meta["pass_rule"] = src.get("pass_rule", "zero_rows")
        entry["query_text"] = src["query_text"]
    elif name in LEGACY_CONTROL_META:
        legacy = LEGACY_CONTROL_META[name]
        meta.setdefault("framework", FRAMEWORK_TITLE)
        meta["framework_id"] = FRAMEWORK_ID
        meta.setdefault("control_ref", legacy["control_ref"])
        meta.setdefault("control_id", legacy["control_id"])
        meta.setdefault("pass_rule", "zero_rows")
        meta["legacy"] = True
    else:
        meta.setdefault("framework", FRAMEWORK_TITLE)
        meta.setdefault("framework_id", FRAMEWORK_ID)
        meta.setdefault("pass_rule", "zero_rows")

    required = meta.get("required_columns") or []
    if isinstance(required, list) and required:
        meta["natural_key"] = meta.get("natural_key") or infer_natural_key([str(c) for c in required])

    return meta


def main() -> None:
    with open(QUERIES_JSON, encoding="utf-8") as f:
        data = json.load(f)

    with open(CIS_QUERIES_JSON, encoding="utf-8") as f:
        cis_data = json.load(f)

    cis = cis_by_name(cis_data)
    existing_names = {q["name"] for q in data["queries"]}

    updated = 0
    for entry in data["queries"]:
        before = json.dumps(entry.get("extra_metadata"), sort_keys=True)
        entry["extra_metadata"] = enrich_extra_metadata(entry, cis)
        after = json.dumps(entry.get("extra_metadata"), sort_keys=True)
        if before != after:
            updated += 1

    added = 0
    for cis_q in cis_data.get("queries", []):
        if cis_q["name"] not in existing_names:
            required = cis_q["required_columns"]
            data["queries"].append(
                {
                    "name": cis_q["name"],
                    "version": "1.0",
                    "provider": "aws",
                    "plugin": "aws",
                    "query_text": cis_q["query_text"],
                    "execution_mode": "single_account",
                    "output_format": "json",
                    "schedule_enabled": False,
                    "active": True,
                    "extra_metadata": {
                        "category": "compliance",
                        "framework": FRAMEWORK_TITLE,
                        "framework_id": FRAMEWORK_ID,
                        "control_id": cis_q["control_id"],
                        "control_ref": cis_q["control_ref"],
                        "required_columns": required,
                        "pass_rule": cis_q.get("pass_rule", "zero_rows"),
                        "natural_key": infer_natural_key(required),
                    },
                }
            )
            existing_names.add(cis_q["name"])
            added += 1

    with open(QUERIES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    compliance = [
        q for q in data["queries"]
        if (q.get("extra_metadata") or {}).get("category") == "compliance"
    ]
    with_framework = sum(1 for q in compliance if (q.get("extra_metadata") or {}).get("framework_id"))
    with_control_ref = sum(1 for q in compliance if (q.get("extra_metadata") or {}).get("control_ref"))

    print(f"Updated metadata on {updated} queries")
    print(f"Added {added} missing CIS queries")
    print(f"Total queries: {len(data['queries'])}")
    print(f"Compliance queries: {len(compliance)} (framework_id: {with_framework}, control_ref: {with_control_ref})")


if __name__ == "__main__":
    main()
