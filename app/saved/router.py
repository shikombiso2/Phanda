import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Listing, SavedOpportunity, User
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


@router.get("", response_model=list[ListingOut])
def list_saved_opportunities(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Listing]:
    saved = db.scalars(select(SavedOpportunity).where(SavedOpportunity.user_id == user.id)).all()
    return [row.listing for row in saved if row.listing and row.listing.is_active]

