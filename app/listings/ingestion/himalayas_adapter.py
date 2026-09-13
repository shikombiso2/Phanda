from __future__ import annotations

import asyncio

import httpx

from app.core.config import get_settings
from app.core.observability import emit_event
from app.listings.ingestion.normalize import NormalizedListing, normalize_himalayas

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES_PER_PAGE = 2
_RETRY_BACKOFF_SECONDS = 1.5
_PAUSE_BETWEEN_PAGES_SECONDS = 0.5

# The browse API caps page size at 20 and ignores anything larger, so this is
# the API's limit rather than a tuning knob -- only the page *count* is
# configurable (Settings.himalayas_ingestion_max_pages).
_PAGE_SIZE = 20

_BASE_URL = "https://himalayas.app/jobs/api"


class HimalayasClient:
    """Public, unauthenticated remote-jobs source.

    Deliberately the same shape as AdzunaClient -- fetch_page with bounded
    retries, fetch_all paginating until the source runs out and returning
    whatever it already has if a page fails. The one structural difference is
    pagination: Himalayas is cursor-based (its `offset` param is deprecated),
    so fetch_page returns the next cursor alongside the rows and fetch_all
    threads it through rather than counting page numbers.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def fetch_page(self, cursor: str | None = None) -> tuple[list[NormalizedListing], str | None]:
        params: dict[str, object] = {"limit": _PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES_PER_PAGE + 1):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get(_BASE_URL, params=params)
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES_PER_PAGE:
                    emit_event("himalayas_page_retry", http_status=response.status_code, attempt=attempt + 1)
                    await asyncio.sleep(_backoff_seconds(response, attempt))
                    continue
                response.raise_for_status()
                body = response.json()
                rows = [normalize_himalayas(job) for job in body.get("jobs", [])]
                return rows, body.get("nextCursor")
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES_PER_PAGE:
                    emit_event("himalayas_page_retry", reason="network_error", attempt=attempt + 1)
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
        assert last_exc is not None
        raise last_exc

    async def fetch_all(self, max_pages: int | None = None) -> list[NormalizedListing]:
        """Follow nextCursor until the source stops returning one, ``max_pages``
        is hit, or a page fails after its retries -- in which case whatever was
        already fetched is still returned rather than discarded, so one bad
        page (or a 429 they refuse to let up on) doesn't cost the whole run.

        A short pause between pages is deliberate: this is a free, keyless API
        that rate-limits, and ingestion runs on a schedule rather than per
        request, so there is nothing to gain by hitting it as fast as possible.
        """
        max_pages = max_pages or self.settings.himalayas_ingestion_max_pages

        all_rows: list[NormalizedListing] = []
        cursor: str | None = None
        for page in range(1, max_pages + 1):
            try:
                rows, cursor = await self.fetch_page(cursor)
            except httpx.HTTPError:
                emit_event("himalayas_ingestion_page_failed", page=page, pages_completed=page - 1)
                break
            all_rows.extend(rows)
            if not cursor:
                break  # the source has no further pages
            if page < max_pages:
                await asyncio.sleep(_PAUSE_BETWEEN_PAGES_SECONDS)
        emit_event("himalayas_ingestion_fetched", listing_count=len(all_rows))
        return all_rows


def _backoff_seconds(response: httpx.Response, attempt: int) -> float:
    """Honour Retry-After on a 429, falling back to exponential backoff.

    Ignoring a rate limiter's own stated wait and retrying on our schedule is
    how a soft limit becomes a block, and this source is shared and free.
    """
    default = _RETRY_BACKOFF_SECONDS * (2**attempt)
    if response.status_code != 429:
        return default
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return default
    try:
        # Only the delta-seconds form is handled; an HTTP-date Retry-After
        # falls back to the default rather than being mis-parsed as seconds.
        return max(default, min(float(retry_after), 60.0))
    except ValueError:
        return default
