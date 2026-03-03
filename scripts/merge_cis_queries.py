#!/usr/bin/env python3
"""Merge CIS v6 queries from cloud-compliance-engine into data/queries.json."""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUERIES_JSON = PROJECT_ROOT / "data" / "queries.json"
CIS_QUERIES_JSON = PROJECT_ROOT / "cloud-compliance-engine" / "queries" / "cis_v6_queries.json"


def cis_to_steampipe_format(cis_query: dict) -> dict:
    """Transform CIS query format to steampipe data/queries.json format."""
    return {
        "name": cis_query["name"],
        "version": "1.0",
        "provider": "aws",
        "plugin": "aws",
        "query_text": cis_query["query_text"],
        "execution_mode": "single_account",
        "output_format": "json",
        "schedule_enabled": False,
        "active": True,
        "extra_metadata": {
            "category": "compliance",
            "framework": "CIS AWS Foundations Benchmark v6.0.0",
            "control_id": cis_query["control_id"],
            "control_ref": cis_query["control_ref"],
            "required_columns": cis_query["required_columns"],
            "pass_rule": cis_query["pass_rule"],
        },
    }


def main():
    with open(QUERIES_JSON, encoding="utf-8") as f:
        data = json.load(f)

    with open(CIS_QUERIES_JSON, encoding="utf-8") as f:
        cis_data = json.load(f)

    existing_names = {q["name"] for q in data["queries"]}
    cis_queries = cis_data["queries"]

    added = 0
    for cis_q in cis_queries:
        if cis_q["name"] not in existing_names:
            data["queries"].append(cis_to_steampipe_format(cis_q))
            existing_names.add(cis_q["name"])
            added += 1

    with open(QUERIES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Merged {added} CIS v6 queries into {QUERIES_JSON}")
    print(f"Total queries: {len(data['queries'])}")


if __name__ == "__main__":
    main()
