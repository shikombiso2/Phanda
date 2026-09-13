"""One-off manual backfill for the vacancyupdate.co.za source.

Run once to pick up every post already on the site since --since (default
2026-08-01), rather than waiting for the twice-weekly scheduled task's
8-day lookback to slowly catch up. Safe to re-run: upsert_listings() is
keyed on (source, source_listing_id), so running this again just re-fetches
and overwrites the same rows -- no dry-run gate needed, unlike scripts that
create new rows in other tables.

Usage:
    python scripts/ingest_vacancyupdate_backfill.py [--since 2026-08-01]
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from app.core.db import SessionLocal
from app.listings.ingestion.repository import upsert_listings
from app.listings.ingestion.vacancyupdate_adapter import DEFAULT_BACKFILL_SINCE, VacancyUpdateClient


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill vacancyupdate.co.za listings since a given date")
    parser.add_argument("--since", type=_parse_date, default=DEFAULT_BACKFILL_SINCE, help="YYYY-MM-DD, default 2026-08-01")
    args = parser.parse_args()

    print(f"Backfilling vacancyupdate.co.za posts with sitemap lastmod >= {args.since.date()}...")
    client = VacancyUpdateClient()
    rows = await client.fetch_all(since=args.since)
    print(f"Fetched and parsed {len(rows)} posts.")

    with SessionLocal() as db:
        upserted = upsert_listings(db, rows)
    print(f"Upserted {upserted} listings.")


if __name__ == "__main__":
    asyncio.run(main())
