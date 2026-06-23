"""Compliance worker: consume steampipe:job_completed → extract → evaluate."""
from __future__ import annotations

import json
import logging
import time

import redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from app.config import get_settings
from app.database import SessionLocal
from app.services.pipeline.process_job import process_job_completed
from app.services.rule_engine.registry import get_registry

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [compliance-worker] %(message)s")


def _redis_client(redis_url: str, poll_timeout: int) -> redis.Redis:
    """Upstash needs socket_timeout > blpop timeout; otherwise idle wait raises TimeoutError."""
    return redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=poll_timeout + 25,
        socket_keepalive=True,
        socket_keepalive_options={},
        retry_on_timeout=True,
        health_check_interval=30,
    )


def run_compliance_worker_loop(poll_timeout: int = 5) -> None:
    settings = get_settings()
    queue_key = settings.COMPLIANCE_QUEUE_KEY
    redis_display = settings.REDIS_URL.split("@")[-1] if "@" in settings.REDIS_URL else settings.REDIS_URL
    logger.info("Compliance worker started; queue=%s redis=%s", queue_key, redis_display)

    client = _redis_client(settings.REDIS_URL, poll_timeout)

    while True:
        try:
            result = client.blpop(queue_key, timeout=poll_timeout)
            if result is None:
                continue
            _, raw = result
            event = json.loads(raw)
            session = SessionLocal()
            try:
                registry = get_registry(session)
                summary = process_job_completed(session, event, registry)
                if summary:
                    session.commit()
                    logger.info(
                        "Processed job=%s control=%s status=%s scan=%s",
                        summary.get("execution_job_id"),
                        summary.get("control_ref"),
                        summary.get("status"),
                        summary.get("scan_status"),
                    )
                else:
                    session.rollback()
            except Exception:
                session.rollback()
                logger.exception("Failed processing event: %s", event)
            finally:
                session.close()
        except TimeoutError:
            continue
        except (ConnectionError, RedisError):
            logger.warning("Redis connection lost; reconnecting in 3s")
            time.sleep(3)
            client = _redis_client(settings.REDIS_URL, poll_timeout)
        except KeyboardInterrupt:
            logger.info("Compliance worker stopped")
            break


if __name__ == "__main__":
    run_compliance_worker_loop()
