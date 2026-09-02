from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Application, ApplicationSubmissionStatus, ApplyMethod, CvVersion, CvVersionStatus, Listing, Profile, TailoredDocument, TailoredDocumentStatus, User
from app.core.observability import emit_event
from app.core.security import get_current_user
from app.core.storage import create_download_url, get_bytes
from app.cv_tailoring.schemas import TailoredDocumentOut, TailoringAllowanceOut, TailoringRequestIn
from app.monetization.gate import get_tailoring_allowance, reserve_tailoring_request

router = APIRouter(tags=["tailoring"])


@router.get("/tailoring/allowance", response_model=TailoringAllowanceOut)
def tailoring_allowance(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TailoringAllowanceOut:
    return TailoringAllowanceOut.model_validate(get_tailoring_allowance(db, user.id))


@router.post("/tailored-documents", response_model=TailoredDocumentOut, status_code=status.HTTP_202_ACCEPTED)
def request_tailoring(
    payload: TailoringRequestIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=255),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TailoredDocument:
    listing = db.get(Listing, payload.listing_id)
    profile = db.get(Profile, user.id)
    cv_version_id = payload.cv_version_id or (profile.active_cv_version_id if profile else None)
    cv_version = db.get(CvVersion, cv_version_id) if cv_version_id else None
    if not listing or not listing.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if not profile or not cv_version or cv_version.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A CV version is required")
    if cv_version.status != CvVersionStatus.ready:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Selected CV is not ready")
    emit_event("tailoring_requested", listing_id=listing.id, cv_version_id=cv_version.id)
    try:
        result = reserve_tailoring_request(
            db, user_id=user.id, listing=listing, profile=profile, cv_version=cv_version, idempotency_key=idempotency_key
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc
    if result.created:
        emit_event("tailoring_reserved", document_id=result.document.id, state=result.document.status.value)
    if result.created:
        from app.cv_tailoring.tasks import process_tailored_document_task
        process_tailored_document_task.delay(str(result.document.id))
    return result.document


@router.get("/tailored-documents/{document_id}", response_model=TailoredDocumentOut)
def get_document(document_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TailoredDocument:
    return _owned_document(db, document_id, user.id)


@router.post("/tailored-documents/{document_id}/email", status_code=status.HTTP_202_ACCEPTED)
def retry_document_email(document_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    document = _owned_document(db, document_id, user.id)
    listing = db.get(Listing, document.listing_id)
    if document.status != TailoredDocumentStatus.ready or not listing or listing.apply_method != ApplyMethod.email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This ready document cannot be emailed for its listing")
    application = db.scalar(select(Application).where(Application.user_id == user.id, Application.tailored_document_id == document.id))
    if not application:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Create the application before sending it")
    if application.submission_status not in {ApplicationSubmissionStatus.email_failed}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already queued or has been sent")
    application.submission_status = ApplicationSubmissionStatus.email_queued
    db.commit()
    emit_event("email_queued", application_id=application.id, document_id=document.id, reason="manual_retry")
    from app.applications.tasks import send_application_email_task
    send_application_email_task.delay(str(application.id))
    return {"status": "queued"}


@router.get("/tailored-documents/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    kind: str = Query("cv", pattern="^(cv|cover_letter)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = _owned_document(db, document_id, user.id)
    key = document.tailored_cv_key if kind == "cv" else document.cover_letter_key
    if document.status != TailoredDocumentStatus.ready or not key:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document is not ready")
    filename = "Phanda_Tailored_CV.pdf" if kind == "cv" else "Cover_Letter.pdf"
    expires_in = 300
    signed_url = create_download_url(key, filename, expires_in=expires_in)
    emit_event("download_signed", document_id=document.id, kind=kind, delivery="signed_url" if signed_url else "proxy")
    if signed_url:
        return {"url": signed_url, "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()}
    # Local storage is intentionally proxied during development: no local URI leaks to clients.
    return Response(get_bytes(key), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _owned_document(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> TailoredDocument:
    document = db.scalar(select(TailoredDocument).where(TailoredDocument.id == document_id, TailoredDocument.user_id == user_id))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tailored document not found")
    return document
