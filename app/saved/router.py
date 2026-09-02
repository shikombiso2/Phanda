import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.models import Listing, SavedOpportunity, User
from app.core.pagination import Page, PageParams, page_of, pagination_params
from app.core.security import get_current_user
from app.listings.schemas import ListingOut

router = APIRouter(prefix="/saved-opportunities", tags=["saved-opportunities"])


@router.post("/{listing_id}")
def save_opportunity(
    listing_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not db.get(Listing, listing_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    existing = db.scalar(
        select(SavedOpportunity).where(SavedOpportunity.user_id == user.id, SavedOpportunity.listing_id == listing_id)
    )
    if not existing:
        db.add(SavedOpportunity(user_id=user.id, listing_id=listing_id))
        db.commit()
    return {"status": "saved"}


@router.delete("/{listing_id}")
def unsave_opportunity(
    listing_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    db.execute(delete(SavedOpportunity).where(SavedOpportunity.user_id == user.id, SavedOpportunity.listing_id == listing_id))
    db.commit()
    return {"status": "removed"}


@router.get("", response_model=Page[ListingOut])
def list_saved_opportunities(
    params: PageParams = Depends(pagination_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page:
    query = (
        select(SavedOpportunity)
        .join(Listing, Listing.id == SavedOpportunity.listing_id)
        .where(SavedOpportunity.user_id == user.id, Listing.is_active.is_(True))
    )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    saved = db.scalars(
        query.options(selectinload(SavedOpportunity.listing))
        .order_by(SavedOpportunity.saved_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    return page_of([row.listing for row in saved], total, params)

