import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.listings.ingestion.adzuna_adapter import AdzunaClient
from app.listings.ingestion.repository import upsert_listings

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/adzuna/run")
async def run_adzuna_ingestion(
    db: Session = Depends(get_db),
    ingestion_secret: str | None = Header(default=None, alias="X-Ingestion-Secret"),
) -> dict[str, int]:
    """Manual trigger for the scheduled ingestion job.

    Ingestion normally runs from Celery beat; this exists only for operator
    use (backfills, on-demand refreshes) and must never be reachable by an
    anonymous caller — without a check here, anyone who can reach the API
    could force outbound Adzuna calls on demand and exhaust its free-tier
    rate limit, starving the scheduled job for everyone.
    """
    settings = get_settings()
    if not settings.ingestion_trigger_secret or not ingestion_secret or not hmac.compare_digest(ingestion_secret, settings.ingestion_trigger_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing ingestion secret")
    rows = await AdzunaClient().fetch_all()
    return {"ingested": upsert_listings(db, rows)}
