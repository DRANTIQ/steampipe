"""Snapshot storage: S3 partitioned by tenant/date, or local path for dev/tests."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import get_settings


def _slugify_path_segment(value: str, fallback: str = "unknown", max_len: int = 64) -> str:
    """Filesystem- and S3-safe path segment from a human-readable label."""
    if not value or not str(value).strip():
        return fallback
    s = str(value).strip().lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        return fallback
    return s[:max_len]


class SnapshotService:
    """Persist execution result JSON to S3 (partitioned) or local path."""

    def __init__(
        self,
        use_local_storage: bool | None = None,
        local_storage_path: str | None = None,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        settings = get_settings()
        self._use_local = use_local_storage if use_local_storage is not None else settings.USE_LOCAL_STORAGE
        self._local_path = Path(local_storage_path or settings.LOCAL_STORAGE_PATH)
        self._bucket = bucket or settings.S3_BUCKET
        self._region = region or settings.S3_REGION
        self._s3_client = None

    def _get_s3_client(self):
        if self._s3_client is None:
            import boto3
            from src.config import get_settings
            s = get_settings()
            kw: dict = {"region_name": self._region}
            if s.AWS_ACCESS_KEY_ID:
                kw["aws_access_key_id"] = s.AWS_ACCESS_KEY_ID
                kw["aws_secret_access_key"] = s.AWS_SECRET_ACCESS_KEY
                if s.AWS_SESSION_TOKEN:
                    kw["aws_session_token"] = s.AWS_SESSION_TOKEN
            self._s3_client = boto3.client("s3", **kw)
        return self._s3_client

    def persist_snapshot(
        self,
        tenant_id: str,
        execution_id: str,
        query_id: str,
        account_id: str,
        provider: str,
        account_identifier: str,
        region: str | None,
        data: dict[str, Any],
        tenant_name: str | None = None,
    ) -> str:
        """Write snapshot; return path/key for storage in ExecutionResult.snapshot_path.

        Path layout (human-readable):
          {tenant_slug}/{provider}/{cloud_account_number}/{year}/{month}/{day}/{execution_id}/result.json

        tenant_name and account_identifier are slugified for safe paths. Internal UUIDs are fallbacks only.
        """
        now = datetime.utcnow()
        tenant_segment = _slugify_path_segment(
            tenant_name or "",
            fallback=_slugify_path_segment(tenant_id, fallback="tenant"),
        )
        provider_segment = _slugify_path_segment(provider, fallback="unknown")
        account_segment = _slugify_path_segment(
            account_identifier or account_id,
            fallback=_slugify_path_segment(account_id, fallback="account"),
        )
        key = (
            f"{tenant_segment}/{provider_segment}/{account_segment}/"
            f"{now.year}/{now.month:02d}/{now.day:02d}/"
            f"{execution_id}/result.json"
        )
        body = json.dumps(data, default=str).encode("utf-8")

        if self._use_local:
            full_path = self._local_path / key
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(body)
            return str(full_path)

        client = self._get_s3_client()
        client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType="application/json")
        return f"s3://{self._bucket}/{key}"

    def get_snapshot_content(self, snapshot_path: str) -> dict[str, Any] | None:
        """Read snapshot JSON by path (local file or s3://). Returns None if missing or invalid."""
        if not snapshot_path:
            return None
        if snapshot_path.startswith("s3://"):
            try:
                # s3://bucket/key
                parts = snapshot_path[5:].split("/", 1)
                bucket, key = parts[0], parts[1]
                client = self._get_s3_client()
                resp = client.get_object(Bucket=bucket, Key=key)
                return json.loads(resp["Body"].read().decode("utf-8"))
            except Exception:
                return None
        try:
            return json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        except Exception:
            return None
