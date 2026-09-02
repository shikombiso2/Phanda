"""Structured JSON logging to stdout.

Before this module existed, ``app/core/observability.py`` called
``logging.getLogger("phanda.events").info(...)`` into a process that never
configured logging at all. With no handler attached, the logger inherited the
root logger's default WARNING level, so every INFO-level operational event
(tailoring progress, email outcomes, reward grants) was silently discarded.
``configure_logging`` fixes that for both the API process and the Celery
worker/beat processes.
"""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from datetime import datetime, timezone

_CONFIGURED = False

# Fields already carried by the LogRecord itself; anything else attached via
# `extra=` (notably `phanda_event`) is folded into the JSON payload.
_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent: safe to call from both the API factory and the Celery entrypoint."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "formatter": "json",
                }
            },
            "root": {"handlers": ["stdout"], "level": level},
            "loggers": {
                # Quiet the noisy access/health chatter; keep operational events at INFO.
                "uvicorn.access": {"level": "WARNING", "propagate": True},
                "phanda.events": {"level": "INFO", "propagate": True},
                "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
            },
        }
    )
