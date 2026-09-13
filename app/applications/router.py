import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.applications.schemas import ApplicationCreate, ApplicationOut, ApplicationStatusUpdate, ApplyOut
from app.core.db import get_db
from app.core.models import Application, ApplicationStatus, ApplicationSubmissionStatus, AppliedVia, ApplyMethod, CvVersion, CvVersionStatus, Listing, Profile, TailoredDocument, TailoredDocumentStatus, User
from app.core.observability import emit_event
from app.core.pagination import Page, PageParams, page_of, pagination_params
from app.core.security import get_current_user

router = APIRouter(prefix="/applications", tags=["applications"])


def _apply_out(application: Application, listing: Listing) -> ApplyOut:
    return ApplyOut(
        id=application.id,
        listing_id=application.listing_id,
        status=application.status,
        tailored_document_id=application.tailored_document_id,
        applied_via=application.applied_via,
        applied_at=application.applied_at,
        apply_method=listing.apply_method,
        # ats_link: the employer's own apply page, for the client to open.
        # manual: informational only (an address, a reference, instructions
        # to follow outside Phanda entirely) -- still shown, just never
        # something the client treats as a clickable "apply" destination.
        # email: null -- Phanda already sent it on the user's behalf, there
        # is nothing left for the client to open.
        apply_target=listing.apply_target if listing.apply_method != ApplyMethod.email else None,
    )


@router.post("/{listing_id}/apply", response_model=ApplyOut, status_code=status.HTTP_202_ACCEPTED)
def apply_to_listing(
    listing_id: uuid.UUID,
    payload: ApplicationCreate | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplyOut:
    listing = db.get(Listing, listing_id)
    profile = db.get(Profile, user.id)
    if not listing or not listing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile not found")

    if idempotency_key:
        duplicate = db.scalar(select(Application).where(Application.user_id == user.id, Application.idempotency_key == idempotency_key))
        if duplicate:
            return _apply_out(duplicate, duplicate.listing)
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
        return _apply_out(existing, listing)

    if listing.apply_method == ApplyMethod.email:
        applied_via = AppliedVia.phanda_email
        initial_status = ApplicationStatus.prepared
        submission_status = ApplicationSubmissionStatus.email_queued
    elif listing.apply_method == ApplyMethod.manual:
        # No click-through happened (there is nothing to click through to),
        # and Phanda sent nothing on the user's behalf -- prepared/
        # not_started is the honest state, not external_started, which
        # would claim a real external apply flow was launched.
        applied_via = AppliedVia.external_link
        initial_status = ApplicationStatus.prepared
        submission_status = ApplicationSubmissionStatus.not_started
    else:  # ats_link
        applied_via = AppliedVia.external_link
        initial_status = ApplicationStatus.external_started
        submission_status = ApplicationSubmissionStatus.external_started

    application = Application(
        user_id=user.id,
        listing_id=listing.id,
        tailored_document_id=tailored_document_id,
        idempotency_key=idempotency_key,
        status=initial_status,
        submission_status=submission_status,
        applied_via=applied_via,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    if listing.apply_method == ApplyMethod.email:
        from app.applications.tasks import send_application_email_task
        emit_event("email_queued", application_id=application.id, source="application_created")
        send_application_email_task.delay(str(application.id))
    return _apply_out(application, listing)


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Application:
    application = db.scalar(
        select(Application)
        .options(selectinload(Application.listing))
        .where(Application.id == application_id, Application.user_id == user.id)
    )
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    application.status = payload.status
    db.commit()
    db.refresh(application)
    return application


@router.get("", response_model=Page[ApplicationOut])
def list_applications(
    params: PageParams = Depends(pagination_params),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page:
    query = select(Application).where(Application.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.options(selectinload(Application.listing))
        .order_by(Application.applied_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    return page_of(rows, total, params)
