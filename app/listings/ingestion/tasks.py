import asyncio

from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.listings.ingestion.adzuna_adapter import AdzunaClient
from app.listings.ingestion.repository import deactivate_stale_listings, upsert_listings


@celery_app.task(name="app.listings.ingestion.tasks.ingest_adzuna")
def ingest_adzuna() -> int:
    async def _run() -> int:
        client = AdzunaClient()
        rows = await client.fetch_all()
        with SessionLocal() as db:
            return upsert_listings(db, rows)

    return asyncio.run(_run())


@celery_app.task(name="app.listings.ingestion.tasks.deactivate_stale_listings")
def deactivate_stale_listings_task() -> int:
    with SessionLocal() as db:
        return deactivate_stale_listings(db)

