"""Job queue over Redis. API pushes job_id; worker pops and processes."""
from __future__ import annotations

import json
import time
from typing import Any

import redis
from redis.exceptions import ConnectionError, RedisError
from src.config import get_settings

QUEUE_KEY = "steampipe:execution_jobs"
JOB_COMPLETED_KEY = "steampipe:job_completed"
ACCOUNT_SESSION_LOCK_PREFIX = "steampipe:account_session"
ACCOUNT_SESSION_MODE = "account_session"


class QueueService:
    def __init__(self, redis_url: str | None = None) -> None:
        self._url = redis_url or get_settings().REDIS_URL
        self._client: redis.Redis | None = None

    def _get_client(self) -> redis.Redis:
        """Get Redis client, reconnecting if connection is dead."""
        if self._client is None:
            self._client = redis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                socket_keepalive_options={},
                retry_on_timeout=True,
                health_check_interval=30,
            )
        else:
            # Check if connection is alive; reconnect if dead
            try:
                self._client.ping()
            except (ConnectionError, RedisError):
                self._client = None
                self._client = redis.from_url(
                    self._url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
        return self._client

    def _with_retry(self, func, max_retries: int = 3, backoff: float = 1.0):
        """Retry Redis operation with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return func()
            except (ConnectionError, RedisError) as e:
                if attempt == max_retries - 1:
                    raise
                self._client = None  # Force reconnect
                time.sleep(backoff * (2 ** attempt))
        return None

    def push(self, job_id: str, payload: dict[str, Any] | None = None) -> None:
        """Enqueue a job by id. Payload optional for worker context."""
        body = {"job_id": job_id, **(payload or {})}
        self._with_retry(lambda: self._get_client().rpush(QUEUE_KEY, json.dumps(body)))

    def push_account_session(self, *, batch_id: str, account_id: str, tenant_id: str) -> None:
        """Enqueue one account session (all batch jobs for this account run on one worker)."""
        body = {
            "mode": ACCOUNT_SESSION_MODE,
            "batch_id": batch_id,
            "account_id": account_id,
            "tenant_id": tenant_id,
        }
        self._with_retry(lambda: self._get_client().rpush(QUEUE_KEY, json.dumps(body)))

    def pop(self, timeout_seconds: int = 5) -> dict[str, Any] | None:
        """Block until a job is available or timeout. Returns None on timeout."""
        try:
            result = self._get_client().blpop(QUEUE_KEY, timeout=timeout_seconds)
            if result is None:
                return None
            _, value = result
            return json.loads(value)
        except (ConnectionError, RedisError):
            # On connection error during blpop, reconnect and return None (will retry next loop)
            self._client = None
            return None

    def queue_depth(self) -> int:
        return self._with_retry(lambda: self._get_client().llen(QUEUE_KEY), max_retries=2) or 0

    def publish_job_completed(self, payload: dict[str, Any]) -> None:
        """Notify downstream consumers (e.g. compliance extract) that a job finished successfully."""
        self._with_retry(
            lambda: self._get_client().rpush(JOB_COMPLETED_KEY, json.dumps(payload)),
            max_retries=2,
        )

    def _account_session_lock_key(self, batch_id: str, account_id: str) -> str:
        return f"{ACCOUNT_SESSION_LOCK_PREFIX}:{batch_id}:{account_id}"

    def account_session_lock_held(self, batch_id: str, account_id: str) -> bool:
        key = self._account_session_lock_key(batch_id, account_id)
        return bool(self._with_retry(lambda: self._get_client().exists(key), max_retries=2))

    def try_acquire_account_session_lock(
        self, batch_id: str, account_id: str, ttl_seconds: int = 7200
    ) -> bool:
        key = self._account_session_lock_key(batch_id, account_id)
        return bool(
            self._with_retry(
                lambda: self._get_client().set(key, "1", nx=True, ex=ttl_seconds),
                max_retries=2,
            )
        )

    def release_account_session_lock(self, batch_id: str, account_id: str) -> None:
        key = self._account_session_lock_key(batch_id, account_id)
        self._with_retry(lambda: self._get_client().delete(key), max_retries=2)
