import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Listing, ListingType, Profile, User
from app.core.security import get_current_user
from app.listings.schemas import ListingMatchOut, ListingOut
from app.matching.service import score_listing

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("", response_model=list[ListingOut])
def list_listings(
    listing_type: ListingType | None = Query(default=None, alias="type"),
    location: str | None = None,
    remote: bool | None = None,
    db: Session = Depends(get_db),
) -> list[Listing]:
    query = select(Listing).where(Listing.is_active.is_(True))
    if listing_type:
        query = query.where(Listing.listing_type == listing_type)
    if location:
        query = query.where(Listing.location.ilike(f"%{location}%"))
    if remote is True:
        query = query.where(Listing.location.ilike("%remote%"))
    return list(db.scalars(query.order_by(Listing.posted_at.desc().nullslast(), Listing.ingested_at.desc())).all())


@router.get("/matches", response_model=list[ListingMatchOut])
def matched_listings(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    profile = db.get(Profile, user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile not found")
    listings = db.scalars(select(Listing).where(Listing.is_active.is_(True))).all()
    scored = [{**ListingOut.model_validate(listing).model_dump(), "match": score_listing(profile, listing)} for listing in listings]
    return sorted(scored, key=lambda row: row["match"]["score"], reverse=True)


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: uuid.UUID, db: Session = Depends(get_db)) -> Listing:
    listing = db.get(Listing, listing_id)
    if not listing or not listing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return listing

