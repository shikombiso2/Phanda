import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Listing, ListingType, Profile, User
from app.core.pagination import Page, PageParams, page_of, pagination_params
from app.core.security import get_current_user
from app.listings.schemas import ListingOut, ListingSummaryOut
from app.recommendations.schemas import MatchedListingOut
from app.recommendations.service import score_listings_for_profile

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("", response_model=Page[ListingSummaryOut])
def list_listings(
    listing_type: ListingType | None = Query(default=None, alias="type"),
    location: str | None = None,
    remote: bool | None = None,
    params: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Listing).where(Listing.is_active.is_(True))
    if listing_type:
        query = query.where(Listing.listing_type == listing_type)
    if location:
        query = query.where(Listing.location.ilike(f"%{location}%"))
    if remote is True:
        query = query.where(Listing.location.ilike("%remote%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Listing.posted_at.desc().nullslast(), Listing.ingested_at.desc()).limit(params.limit).offset(params.offset)
    ).all()
    return page_of(rows, total, params)


@router.get("/matches", response_model=Page[MatchedListingOut])
def matched_listings(
    params: PageParams = Depends(pagination_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page:
    profile = db.get(Profile, user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile not found")
    listings = db.scalars(select(Listing).where(Listing.is_active.is_(True))).all()
    ranked = score_listings_for_profile(db, profile, listings)
    total = len(ranked)
    page_rows = ranked[params.offset : params.offset + params.limit]
    items = [
        MatchedListingOut(**ListingOut.model_validate(listing).model_dump(), match=explanation)
        for listing, explanation in page_rows
    ]
    return page_of(items, total, params)


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: uuid.UUID, db: Session = Depends(get_db)) -> Listing:
    listing = db.get(Listing, listing_id)
    if not listing or not listing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return listing
