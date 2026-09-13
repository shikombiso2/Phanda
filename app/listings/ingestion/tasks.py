import asyncio
from datetime import timedelta

from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.models import utcnow
from app.listings.ingestion.adzuna_adapter import AdzunaClient
from app.listings.ingestion.himalayas_adapter import HimalayasClient
from app.listings.ingestion.repository import deactivate_expired_listings, deactivate_stale_listings, upsert_listings
from app.listings.ingestion.vacancyupdate_adapter import ONGOING_LOOKBACK_DAYS, VacancyUpdateClient


@celery_app.task(name="app.listings.ingestion.tasks.ingest_adzuna")
def ingest_adzuna() -> int:
    async def _run() -> int:
        client = AdzunaClient()
        rows = await client.fetch_all()
        with SessionLocal() as db:
            return upsert_listings(db, rows)

    return asyncio.run(_run())


@celery_app.task(name="app.listings.ingestion.tasks.ingest_himalayas")
def ingest_himalayas() -> int:
    async def _run() -> int:
        client = HimalayasClient()
        rows = await client.fetch_all()
        with SessionLocal() as db:
            return upsert_listings(db, rows)

    return asyncio.run(_run())


@celery_app.task(name="app.listings.ingestion.tasks.ingest_vacancyupdate")
def ingest_vacancyupdate() -> int:
    """The ONGOING discovery mode: only posts whose sitemap lastmod falls in
    the last ONGOING_LOOKBACK_DAYS. A one-off full BACKFILL since a fixed
    date is scripts/ingest_vacancyupdate_backfill.py, not this task -- this
    one runs on a schedule and must stay cheap per run."""

    async def _run() -> int:
        client = VacancyUpdateClient()
        since = utcnow() - timedelta(days=ONGOING_LOOKBACK_DAYS)
        rows = await client.fetch_all(since=since)
        with SessionLocal() as db:
            return upsert_listings(db, rows)

    return asyncio.run(_run())


@celery_app.task(name="app.listings.ingestion.tasks.deactivate_stale_listings")
def deactivate_stale_listings_task() -> int:
    with SessionLocal() as db:
        return deactivate_stale_listings(db)


@celery_app.task(name="app.listings.ingestion.tasks.deactivate_expired_listings")
def deactivate_expired_listings_task() -> int:
    with SessionLocal() as db:
        return deactivate_expired_listings(db)

