from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.listings.ingestion.adzuna_adapter import AdzunaClient
from app.listings.ingestion.repository import upsert_listings

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/adzuna/run")
async def run_adzuna_ingestion(db: Session = Depends(get_db)) -> dict[str, int]:
    rows = await AdzunaClient().fetch_page()
    return {"ingested": upsert_listings(db, rows)}

