"""Resolve and filter queries from catalog metadata (category, framework_id)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models import Query

# Map API framework_id to extra_metadata.framework / framework_id values in queries.json
FRAMEWORK_ALIASES: dict[str, list[str]] = {
    "cis_aws_v6": [
        "cis_aws_v6",
        "CIS AWS Foundations Benchmark v6.0.0",
    ],
}


def query_matches_framework(meta: dict[str, Any] | None, framework_id: str) -> bool:
    if not meta:
        return False
    if meta.get("framework_id") == framework_id:
        return True
    aliases = FRAMEWORK_ALIASES.get(framework_id, [framework_id])
    fw = meta.get("framework")
    if fw in aliases:
        return True
    return meta.get("framework_id") in aliases


def filter_queries(
    queries: list[Query],
    *,
    provider: str,
    category: str | None = None,
    framework_id: str | None = None,
    active_only: bool = True,
    exclude_legacy: bool = False,
) -> list[Query]:
    """Return queries matching provider and optional category / framework_id filters."""
    result: list[Query] = []
    for query in queries:
        if active_only and not query.active:
            continue
        if query.provider != provider:
            continue
        meta = query.extra_metadata or {}
        if category is not None and meta.get("category") != category:
            continue
        if framework_id is not None and not query_matches_framework(meta, framework_id):
            continue
        if exclude_legacy and meta.get("legacy"):
            continue
        if category == "compliance" and not meta.get("control_ref"):
            continue
        result.append(query)
    return result
