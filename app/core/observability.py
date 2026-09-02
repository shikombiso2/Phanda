"""Small, PII-safe structured event logging for asynchronous workflows."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID


logger = logging.getLogger("phanda.events")


def emit_event(event: str, **fields: str | int | float | bool | UUID | datetime | None) -> None:
    """Log an allowlisted event payload without CV, prompt, or provider content.

    Callers must provide operational identifiers and coarse state only.  Values
    outside the simple scalar set are rejected to prevent accidental logging of
    dictionaries containing candidate or provider data.
    """
    safe_fields: dict[str, str | int | float | bool | None] = {"event": event}
    for key, value in fields.items():
        if value is None:
            continue
        if not isinstance(value, (str, int, float, bool, UUID, datetime)):
            raise TypeError(f"Unsupported observability field: {key}")
        safe_fields[key] = value.isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, UUID) else value
    logger.info("phanda_event", extra={"phanda_event": safe_fields})
