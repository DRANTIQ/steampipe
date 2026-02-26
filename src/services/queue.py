"""Job queue over Redis. API pushes job_id; worker pops and processes."""
from __future__ import annotations

import json
import time
from typing import Any

import redis
from redis.exceptions import ConnectionError, RedisError
from src.config import get_settings

QUEUE_KEY = "steampipe:execution_jobs"


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
