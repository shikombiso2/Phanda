import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.applications.schemas import ApplicationCreate, ApplicationOut, ApplyOut
from app.core.db import get_db
from app.core.models import Application, ApplicationStatus, ApplicationSubmissionStatus, AppliedVia, ApplyMethod, CvVersion, CvVersionStatus, Listing, Profile, TailoredDocument, TailoredDocumentStatus, User
from app.core.observability import emit_event
from app.core.security import get_current_user

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/{listing_id}/apply", response_model=ApplyOut, status_code=status.HTTP_202_ACCEPTED)
def apply_to_listing(
    listing_id: uuid.UUID,
    payload: ApplicationCreate | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Application:
    listing = db.get(Listing, listing_id)
    profile = db.get(Profile, user.id)
    if not listing or not listing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile not found")

    if idempotency_key:
        duplicate = db.scalar(select(Application).where(Application.user_id == user.id, Application.idempotency_key == idempotency_key))
        if duplicate:
            return duplicate
    tailored_document_id = payload.tailored_document_id if payload else None
    if tailored_document_id:
        document = db.scalar(select(TailoredDocument).where(TailoredDocument.id == tailored_document_id, TailoredDocument.user_id == user.id))
        if not document or document.listing_id != listing.id or document.status != TailoredDocumentStatus.ready:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A ready tailored document for this listing is required")
    else:
        master = db.get(CvVersion, profile.active_cv_version_id) if profile.active_cv_version_id else None
        if not master or master.user_id != user.id or master.status != CvVersionStatus.ready:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload a ready master CV or select a ready tailored CV")
    existing = db.scalar(select(Application).where(Application.user_id == user.id, Application.listing_id == listing.id))
    if existing:
        return existing
    applied_via = AppliedVia.phanda_email if listing.apply_method == ApplyMethod.email else AppliedVia.external_link
    application = Application(
        user_id=user.id,
        listing_id=listing.id,
        tailored_document_id=tailored_document_id,
        idempotency_key=idempotency_key,
        status=ApplicationStatus.prepared if listing.apply_method == ApplyMethod.email else ApplicationStatus.external_started,
        submission_status=ApplicationSubmissionStatus.email_queued if listing.apply_method == ApplyMethod.email else ApplicationSubmissionStatus.external_started,
        applied_via=applied_via,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    if listing.apply_method == ApplyMethod.email:
        from app.applications.tasks import send_application_email_task
        emit_event("email_queued", application_id=application.id, source="application_created")
        send_application_email_task.delay(str(application.id))
    return application


@router.get("", response_model=list[ApplicationOut])
def list_applications(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Application]:
    return list(db.scalars(select(Application).where(Application.user_id == user.id).order_by(Application.applied_at.desc())))
