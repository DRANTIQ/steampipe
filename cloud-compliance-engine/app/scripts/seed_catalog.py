"""
Seed compliance.controls and compliance.framework_versions from config/catalog.yaml.
Loads every framework in the catalog (controls YAML + optional rules JSON) so the DB has
all control definitions. Adding new frameworks/providers/categories = add to catalog + run this.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pathlib import Path

import yaml

# Ensure app is importable (run from repo root with PYTHONPATH=cloud-compliance-engine)
BASE = Path(__file__).resolve().parent.parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import SessionLocal
from app.models.compliance import Control, FrameworkVersion, RuleVersion
from app.services.rule_engine.catalog import REPO_ROOT, load_compliance_rules_from_data_queries
from app.services.rule_registry import load_controls_from_yaml, load_rules_from_data_queries
from app.services.hash_utils import rule_definition_hash


def load_catalog() -> list[dict]:
    path = BASE / "config" / "catalog.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    return data.get("frameworks") or []


def seed_framework(db: Session, entry: dict) -> tuple[int, int]:
    """Seed one framework: framework_versions + controls (+ optional rule_version). Returns (controls_count, rules_count)."""
    framework_id = entry["framework_id"]
    provider = entry.get("provider")
    category = entry.get("category")
    version_name = entry.get("version_name", "1.0.0")
    framework_title = entry.get("framework_title", framework_id)
    controls_path = entry.get("controls_path")
    rules_source = entry.get("rules_source") or entry.get("rules_path")

    if not controls_path:
        return 0, 0

    controls_file = BASE / controls_path
    if not controls_file.exists():
        print(f"  Skip {framework_id}: {controls_path} not found")
        return 0, 0

    # Upsert framework_version
    fw_hash = rule_definition_hash({"framework_id": framework_id, "version": version_name})
    stmt_fw = pg_insert(FrameworkVersion).values(
        framework_id=framework_id,
        version_name=version_name,
        provider=provider,
        category=category,
        source_uri=entry.get("source_uri"),
        hash=fw_hash,
    ).on_conflict_do_update(
        index_elements=["framework_id", "version_name"],
        set_={"provider": provider, "category": category, "hash": fw_hash},
    )
    db.execute(stmt_fw)
    db.flush()

    # Load and upsert controls
    _, _version, controls_list = load_controls_from_yaml(controls_file)
    count = 0
    for c in controls_list:
        control_id = c.get("control_id")
        if not control_id:
            continue
        stmt = pg_insert(Control).values(
            framework_id=framework_id,
            control_id=str(control_id),
            provider=provider,
            category=category,
            title=c.get("title"),
            description=c.get("description"),
            severity=c.get("severity", "Low"),
            remediation=c.get("remediation"),
            rationale=c.get("rationale"),
            references=c.get("references"),
            tags=c.get("tags") if isinstance(c.get("tags"), dict) else None,
            enabled=True,
        ).on_conflict_do_update(
            index_elements=["framework_id", "control_id"],
            set_={
                "title": c.get("title"),
                "description": c.get("description"),
                "severity": c.get("severity", "Low"),
                "remediation": c.get("remediation"),
                "provider": provider,
                "category": category,
            },
        )
        db.execute(stmt)
        count += 1

    # Optional: one rule_version per framework (so evaluation_runs can reference it)
    rules_count = 0
    if rules_source:
        rules_file = REPO_ROOT / rules_source if not Path(rules_source).is_absolute() else Path(rules_source)
        if rules_file.exists():
            _, rules = load_rules_from_data_queries(rules_file)
            if rules:
                combined = rule_definition_hash([r.get("rule_definition_hash") for r in rules])
                definitions = [
                    {
                        "control_ref": r.get("control_ref"),
                        "control_id": r.get("control_id"),
                        "pass_rule": r.get("pass_rule"),
                        "required_columns": r.get("required_columns") or [],
                        "rule_definition_hash": r.get("rule_definition_hash"),
                        "query_id": r.get("query_id"),
                        "name": r.get("name"),
                    }
                    for r in rules
                ]
                stmt_rv = pg_insert(RuleVersion).values(
                    framework_id=framework_id,
                    version_name=version_name,
                    hash=combined,
                    notes=f"Loaded from {rules_source}",
                    definitions=definitions,
                ).on_conflict_do_update(
                    index_elements=["framework_id", "version_name"],
                    set_={
                        "hash": combined,
                        "notes": f"Loaded from {rules_source}",
                        "definitions": definitions,
                    },
                )
                db.execute(stmt_rv)
                rules_count = len(rules)
        else:
            print(f"  Warning: rules_source not found: {rules_file}")

    return count, rules_count


def main() -> None:
    get_settings()
    catalog = load_catalog()
    if not catalog:
        print("No frameworks in config/catalog.yaml")
        return

    db = SessionLocal()
    try:
        total_c = 0
        total_r = 0
        for entry in catalog:
            fid = entry.get("framework_id", "?")
            print(f"Seeding {fid} ...")
            c, r = seed_framework(db, entry)
            total_c += c
            total_r += r
            print(f"  -> {c} controls, {r} rules (from JSON)")
        db.commit()
        print(f"Done. Total: {total_c} controls, {len(catalog)} framework(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
