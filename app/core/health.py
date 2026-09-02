"""Liveness and readiness checks.

``/health`` answers "is the process up" and must never touch a dependency —
that is what makes it safe for a liveness probe. ``/ready`` answers "can this
process actually serve traffic" by touching Postgres, Redis and storage, so
an orchestrator does not route requests to an instance whose database is
unreachable.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response) -> dict[str, object]:
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "storage": _check_storage(),
    }
    healthy = all(checks.values())
    response.status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "unavailable", "checks": checks}


def _check_database() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        return True
    except Exception:
        return False


def _check_redis() -> bool:
    try:
        client = redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


def _check_storage() -> bool:
    settings = get_settings()
    if settings.s3_bucket:
        import boto3

        try:
            boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                region_name=settings.s3_region,
            ).head_bucket(Bucket=settings.s3_bucket)
            return True
        except Exception:
            return False
    try:
        from pathlib import Path

        Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False
