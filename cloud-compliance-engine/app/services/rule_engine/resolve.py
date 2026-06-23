"""Resolve evaluation rules: Bronze pinning, rule_versions, live catalog."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.compliance import FrameworkVersion, RuleVersion, Snapshot
from app.services.extract import get_snapshot_content
from app.services.rule_engine.catalog import (
    DEFAULT_FRAMEWORK_VERSION,
    build_pinned_rule_metadata,
    load_compliance_rules_from_metadata,
)
from app.services.rule_engine.registry import RuleRegistry


@dataclass
class ResolvedRule:
    rule: dict[str, Any]
    rule_source: str  # bronze | rule_version | live_catalog
    rule_version_id: UUID | None
    framework_version_id: UUID | None


def get_active_rule_version(
    db: Session,
    framework_id: str,
    version_name: str | None = None,
) -> RuleVersion | None:
    q = select(RuleVersion).where(RuleVersion.framework_id == framework_id)
    if version_name:
        q = q.where(RuleVersion.version_name == version_name)
    else:
        q = q.order_by(RuleVersion.created_at.desc())
    return db.execute(q).scalars().first()


def get_active_framework_version(
    db: Session,
    framework_id: str,
    version_name: str | None = None,
) -> FrameworkVersion | None:
    q = select(FrameworkVersion).where(FrameworkVersion.framework_id == framework_id)
    if version_name:
        q = q.where(FrameworkVersion.version_name == version_name)
    else:
        q = q.order_by(FrameworkVersion.published_at.desc().nullslast(), FrameworkVersion.id.desc())
    return db.execute(q).scalars().first()


def get_rule_from_version_definitions(rule_version: RuleVersion, control_ref: str) -> dict[str, Any] | None:
    for entry in rule_version.definitions or []:
        if entry.get("control_ref") == control_ref:
            return dict(entry)
    return None


def ensure_snapshot_rule_metadata(db: Session, snapshot: Snapshot) -> dict[str, Any] | None:
    """Backfill pinned Bronze rule metadata for legacy snapshots (one-time read from file)."""
    if snapshot.rule_metadata:
        return snapshot.rule_metadata
    if not snapshot.execution_job_id or not snapshot.s3_prefix:
        return None

    settings = get_settings()
    content = get_snapshot_content(
        snapshot.s3_prefix,
        settings.USE_LOCAL_STORAGE,
        settings.LOCAL_STORAGE_PATH,
        settings.S3_BUCKET,
    )
    if not content:
        return None

    bronze_meta = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
    if not bronze_meta.get("control_ref") and snapshot.control_ref:
        bronze_meta = {**bronze_meta, "control_ref": snapshot.control_ref}
    if not bronze_meta.get("control_id") and snapshot.control_id:
        bronze_meta = {**bronze_meta, "control_id": snapshot.control_id}
    if not bronze_meta.get("framework_id") and snapshot.framework_id:
        bronze_meta = {**bronze_meta, "framework_id": snapshot.framework_id}
    if not bronze_meta.get("control_ref"):
        return None

    pinned = build_pinned_rule_metadata(bronze_meta)
    snapshot.rule_metadata = pinned
    db.flush()
    return pinned


def resolve_evaluation_rule(
    db: Session,
    snapshot: Snapshot,
    control_ref: str,
    framework_id: str,
    rule_registry: RuleRegistry,
    *,
    framework_version_name: str | None = DEFAULT_FRAMEWORK_VERSION,
) -> ResolvedRule | None:
    """
    Rule resolution order:
    1. Bronze-pinned rule_metadata (job-linked snapshots) — scan-time immutability
    2. compliance.rule_versions.definitions — versioned catalog
    3. Live public.queries / data/queries.json via registry
    """
    rule_version = get_active_rule_version(db, framework_id, framework_version_name)
    framework_version = get_active_framework_version(db, framework_id, framework_version_name)
    rule_version_id = rule_version.id if rule_version else None
    framework_version_id = framework_version.id if framework_version else None

    if snapshot.execution_job_id:
        pinned = ensure_snapshot_rule_metadata(db, snapshot)
        if pinned and pinned.get("control_ref"):
            rule = load_compliance_rules_from_metadata(pinned)
            if rule:
                return ResolvedRule(
                    rule=rule,
                    rule_source="bronze",
                    rule_version_id=rule_version_id,
                    framework_version_id=framework_version_id,
                )

    if rule_version:
        version_rule = get_rule_from_version_definitions(rule_version, control_ref)
        if version_rule:
            return ResolvedRule(
                rule=version_rule,
                rule_source="rule_version",
                rule_version_id=rule_version_id,
                framework_version_id=framework_version_id,
            )

    live_rule = rule_registry.get(control_ref)
    if live_rule:
        return ResolvedRule(
            rule=dict(live_rule),
            rule_source="live_catalog",
            rule_version_id=rule_version_id,
            framework_version_id=framework_version_id,
        )

    if snapshot.control_ref or snapshot.control_id:
        fallback = load_compliance_rules_from_metadata(
            {
                "control_ref": snapshot.control_ref or control_ref,
                "control_id": snapshot.control_id,
                "framework_id": framework_id,
                "pass_rule": "zero_rows",
            }
        )
        if fallback:
            return ResolvedRule(
                rule=fallback,
                rule_source="snapshot_fields",
                rule_version_id=rule_version_id,
                framework_version_id=framework_version_id,
            )

    return None
