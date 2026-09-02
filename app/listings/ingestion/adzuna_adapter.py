from __future__ import annotations

import asyncio

import httpx

from app.core.config import get_settings
from app.core.observability import emit_event
from app.listings.ingestion.normalize import NormalizedListing, normalize_adzuna

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES_PER_PAGE = 2
_RETRY_BACKOFF_SECONDS = 1.5
_PAUSE_BETWEEN_PAGES_SECONDS = 0.5


class AdzunaClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def fetch_page(self, page: int = 1, results_per_page: int = 50) -> list[NormalizedListing]:
        if not self.settings.adzuna_app_id or not self.settings.adzuna_app_key:
            return []

        url = f"https://api.adzuna.com/v1/api/jobs/{self.settings.adzuna_country}/search/{page}"
        params = {
            "app_id": self.settings.adzuna_app_id,
            "app_key": self.settings.adzuna_app_key,
            "results_per_page": results_per_page,
            "content-type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES_PER_PAGE + 1):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get(url, params=params)
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES_PER_PAGE:
                    emit_event("adzuna_page_retry", page=page, http_status=response.status_code, attempt=attempt + 1)
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
                response.raise_for_status()
                return [normalize_adzuna(row) for row in response.json().get("results", [])]
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES_PER_PAGE:
                    emit_event("adzuna_page_retry", page=page, reason="network_error", attempt=attempt + 1)
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
        assert last_exc is not None
        raise last_exc

    async def fetch_all(self, max_pages: int | None = None, results_per_page: int | None = None) -> list[NormalizedListing]:
        """Paginate until a short page signals the end, ``max_pages`` is hit,
        or a page fails after retries -- in which case whatever was already
        fetched is still returned rather than discarded, so one bad page
        near the end of a run doesn't cost the whole ingestion cycle.

        A short pause between pages is deliberate: Adzuna's free tier is
        rate-limited, and this runs on a schedule, not per-request, so there
        is no reason to hit it as fast as possible.
        """
        if not self.settings.adzuna_app_id or not self.settings.adzuna_app_key:
            return []
        max_pages = max_pages or self.settings.adzuna_ingestion_max_pages
        results_per_page = results_per_page or self.settings.adzuna_ingestion_results_per_page

        all_rows: list[NormalizedListing] = []
        for page in range(1, max_pages + 1):
            try:
                rows = await self.fetch_page(page, results_per_page)
            except httpx.HTTPError:
                emit_event("adzuna_ingestion_page_failed", page=page, pages_completed=page - 1)
                break
            all_rows.extend(rows)
            if len(rows) < results_per_page:
                break  # short page: this was the last one Adzuna has
            if page < max_pages:
                await asyncio.sleep(_PAUSE_BETWEEN_PAGES_SECONDS)
        emit_event("adzuna_ingestion_fetched", listing_count=len(all_rows))
        return all_rows
