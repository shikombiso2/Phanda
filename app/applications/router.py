import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.applications.email import send_application_email
from app.applications.schemas import ApplicationOut, ApplyOut
from app.core.db import get_db
from app.core.errors import raise_access_blocked
from app.core.models import Application, AppliedVia, ApplyMethod, Listing, Profile, User
from app.core.security import get_current_user
from app.cv_tailoring.service import generate_tailored_documents
from app.monetization.gate import check_access

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/{listing_id}/apply", response_model=ApplyOut)
async def apply_to_listing(
    listing_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    listing = db.get(Listing, listing_id)
    profile = db.get(Profile, user.id)
    if not listing or not listing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile not found")

    access = check_access(db, user.id, "cv_tailor")
    if not access.allowed:
        raise_access_blocked(access)

    cv_url, cover_url = generate_tailored_documents(profile, listing)
    applied_via = AppliedVia.phanda_email if listing.apply_method == ApplyMethod.email else AppliedVia.external_link
    application = Application(
        user_id=user.id,
        listing_id=listing.id,
        tailored_cv_url=cv_url,
        tailored_cover_letter_url=cover_url,
        applied_via=applied_via,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    if listing.apply_method == ApplyMethod.email:
        await send_application_email(
            to_email=listing.apply_target,
            subject=f"Application: {listing.title}",
            body="Please find my tailored application documents linked below.",
            cv_url=cv_url,
            cover_letter_url=cover_url,
        )

    result = ApplyOut.model_validate(application).model_dump()
    result["next_step_url"] = listing.apply_target if listing.apply_method == ApplyMethod.ats_link else None
    result["access_reason"] = access.reason
    return result


@router.get("", response_model=list[ApplicationOut])
def list_applications(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Application]:
    return list(db.scalars(select(Application).where(Application.user_id == user.id).order_by(Application.applied_at.desc())))
