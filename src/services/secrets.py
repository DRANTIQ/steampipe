"""Resolve credentials for cloud accounts. Supports extra_metadata and optional AWS Secrets Manager via secret_arn."""
from __future__ import annotations

import json
import logging
from typing import Any

from src.config import get_settings

logger = logging.getLogger(__name__)


def _secretsmanager_client(region_name: str | None = None):
    """Secrets Manager client using master account credentials from settings (same as S3 and Steampipe)."""
    import boto3
    s = get_settings()
    kw: dict = {"region_name": region_name or s.S3_REGION}
    if s.AWS_ACCESS_KEY_ID:
        kw["aws_access_key_id"] = s.AWS_ACCESS_KEY_ID
        kw["aws_secret_access_key"] = s.AWS_SECRET_ACCESS_KEY
        if s.AWS_SESSION_TOKEN:
            kw["aws_session_token"] = s.AWS_SESSION_TOKEN
    return boto3.client("secretsmanager", **kw)


def _region_from_secret_arn(arn: str) -> str | None:
    """arn:aws:secretsmanager:REGION:account:secret:... -> REGION"""
    parts = arn.split(":")
    return parts[3] if len(parts) > 4 else None


class SecretsService:
    """Resolve credentials for a CloudAccount. Returns dict suitable for Steampipe connection config."""

    def get_connection_config(self, account_id: str, provider: str, secret_arn: str | None, extra_metadata: dict | None) -> dict[str, Any]:
        """Return connection config for Steampipe .spc. Merges secret_arn (if set) with extra_metadata."""
        config: dict[str, Any] = {"connection_name": f"{provider}_{account_id}"}
        # Load from Secrets Manager when secret_arn is set (e.g. role_arn, external_id, or full connection JSON)
        if secret_arn and secret_arn.startswith("arn:aws:secretsmanager:"):
            try:
                region = _region_from_secret_arn(secret_arn)
                client = _secretsmanager_client(region_name=region)
                resp = client.get_secret_value(SecretId=secret_arn)
                raw = resp.get("SecretString") or ""
                if raw.strip().startswith("{"):
                    secret_data = json.loads(raw)
                    if isinstance(secret_data, dict):
                        config.update(secret_data)
                        logger.debug(
                            "Loaded connection config from Secrets Manager: secret_arn=%s region=%s keys=%s",
                            secret_arn,
                            region,
                            list(secret_data.keys()),
                        )
                else:
                    config["secret"] = raw
                    logger.debug("Loaded secret (non-JSON) from Secrets Manager: secret_arn=%s", secret_arn)
            except Exception as e:
                logger.debug("Secrets Manager get_secret_value failed (falling back to extra_metadata): %s", e)
        if extra_metadata:
            config.update(extra_metadata)
            logger.debug("Merged extra_metadata keys into connection config: %s", list(extra_metadata.keys()))
        logger.debug("get_connection_config result keys (no values): %s", list(config.keys()))
        return config
