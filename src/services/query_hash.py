"""Content hash for queries: normalize query_text and compute SHA-256 for deduplication."""
from __future__ import annotations

import hashlib
import re


def normalize_query_text(text: str) -> str:
    """Strip and collapse whitespace, trim trailing semicolons."""
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    if t.endswith(";"):
        t = t[:-1].strip()
    return t


def content_hash_for_query_text(query_text: str) -> str:
    """Return SHA-256 hex digest of normalized query_text."""
    normalized = normalize_query_text(query_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
