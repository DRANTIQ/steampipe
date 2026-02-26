#!/usr/bin/env python3
"""Apply the queries document (data/queries.json) to the queries table. Upserts by (name, version)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.models import Query
from src.services.database import get_db_session_factory
from src.services.query_hash import content_hash_for_query_text


# Default path relative to project root
QUERIES_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "queries.json"


def load_queries_document(path: Path) -> list[dict]:
    """Load and parse the queries document. Returns list of query dicts."""
    if not path.exists():
        raise FileNotFoundError(f"Queries document not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "queries" not in data or not isinstance(data["queries"], list):
        raise ValueError("Document must have a 'queries' array")
    return data["queries"]


def apply_queries(session: Session, entries: list[dict]) -> tuple[int, int]:
    """Upsert entries into queries table. Returns (inserted_count, updated_count)."""
    inserted = 0
    updated = 0
    for entry in entries:
        name = entry["name"]
        version = entry.get("version", "1.0")
        existing = (
            session.query(Query)
            .filter(Query.name == name, Query.version == version, Query.deleted_at.is_(None))
            .first()
        )
        query_text = entry["query_text"]
        payload = {
            "provider": entry["provider"],
            "plugin": entry["plugin"],
            "query_text": query_text,
            "execution_mode": entry.get("execution_mode", "single_account"),
            "output_format": entry.get("output_format", "json"),
            "schedule_enabled": entry.get("schedule_enabled", False),
            "active": entry.get("active", True),
            "extra_metadata": entry.get("extra_metadata"),
            "content_hash": content_hash_for_query_text(query_text),
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            updated += 1
        else:
            session.add(
                Query(
                    name=name,
                    version=version,
                    **payload,
                )
            )
            inserted += 1
    return inserted, updated


def _session_factory_for_url(url: str) -> sessionmaker[Session]:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def main() -> None:
    get_settings()
    path = Path(os.environ.get("QUERIES_JSON_PATH", str(QUERIES_JSON_PATH)))
    entries = load_queries_document(path)
    seed_url = os.environ.get("SEED_DATABASE_URL")
    if seed_url:
        factory = _session_factory_for_url(seed_url)
    else:
        factory = get_db_session_factory()
    with factory() as session:
        inserted, updated = apply_queries(session, entries)
        session.commit()
    print(f"Queries document applied: {len(entries)} total, {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    main()
