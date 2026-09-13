from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import CvVersion, CvVersionStatus, Profile, utcnow
from app.core.observability import emit_event
from app.core.storage import get_bytes, put_bytes
from app.cv_tailoring.extraction import CvExtractionError, extract_cv
from app.cv_tailoring.service import TransientTailoringError, fail_stale_documents, process_tailored_document


@celery_app.task(name="app.cv_tailoring.tasks.extract_cv_version")
def extract_cv_version(cv_version_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        version = db.get(CvVersion, cv_version_id)
        if not version or version.status in {CvVersionStatus.ready, CvVersionStatus.failed}:
            return
        version.status = CvVersionStatus.extracting
        version.attempt_count += 1
        version.processing_lease_expires_at = utcnow() + timedelta(minutes=settings.cv_extraction_lease_minutes)
        db.commit()
        try:
            extracted = extract_cv(get_bytes(version.storage_key), version.content_type)
            text_key = put_bytes(
                extracted.text.encode("utf-8"),
                f"users/{version.user_id}/cv-versions/{version.id}/extracted.txt",
                "text/plain; charset=utf-8",
            )
            version = db.get(CvVersion, cv_version_id)
            if not version:
                return
            version.status = CvVersionStatus.ready
            version.page_count = extracted.page_count
            version.extracted_text_key = text_key
            version.ready_at = utcnow()
            version.processing_lease_expires_at = None
            profile = db.get(Profile, version.user_id)
            active = db.get(CvVersion, profile.active_cv_version_id) if profile and profile.active_cv_version_id else None
            if profile and (not active or version.version_number >= active.version_number):
                profile.active_cv_version_id = version.id
            db.commit()
            emit_event("cv_extraction_completed", cv_version_id=version.id, attempt=version.attempt_count)
        except CvExtractionError as exc:
            version = db.get(CvVersion, cv_version_id)
            if version:
                version.status = CvVersionStatus.failed
                version.failure_code = exc.code
                version.processing_lease_expires_at = None
                db.commit()
                emit_event("cv_extraction_failed", cv_version_id=version.id, code=exc.code)
        except Exception:
            version = db.get(CvVersion, cv_version_id)
            if version:
                version.status = CvVersionStatus.failed
                version.failure_code = "extraction_failed"
                version.processing_lease_expires_at = None
                db.commit()
                emit_event("cv_extraction_failed", cv_version_id=version.id, code="extraction_failed")


@celery_app.task(bind=True, name="app.cv_tailoring.tasks.process_tailored_document", max_retries=2)
def process_tailored_document_task(self, document_id: str) -> None:
    try:
        with SessionLocal() as db:
            process_tailored_document(db, document_id)
    except TransientTailoringError as exc:
        # retry_after_seconds is only ever set for provider_rate_limited (see
        # gemini.py): a 429 needs to wait out the provider's own limit
        # window, not the exponential backoff used for a generic transient
        # failure (503/timeout/network), which retries much sooner.
        countdown = exc.retry_after_seconds if exc.retry_after_seconds is not None else 2 ** self.request.retries
        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(name="app.cv_tailoring.tasks.reconcile_stale_tailoring")
def reconcile_stale_tailoring() -> int:
    with SessionLocal() as db:
        retry_ids = fail_stale_documents(db)
    for document_id in retry_ids:
        process_tailored_document_task.delay(document_id)
    return len(retry_ids)


def find_stale_cv_versions(db) -> list[uuid.UUID]:
    """CV versions whose extraction lease has expired: either a worker
    crashed mid-extraction, or the ``.delay()`` call after upload never made
    it to Redis (the version never even reached "extracting"). Both look the
    same from here -- a version stuck past its lease -- so both requeue the
    same way."""
    now = utcnow()
    return list(
        db.scalars(
            select(CvVersion.id).where(
                CvVersion.status.in_([CvVersionStatus.uploaded, CvVersionStatus.extracting]),
                CvVersion.processing_lease_expires_at.is_not(None),
                CvVersion.processing_lease_expires_at < now,
            )
        ).all()
    )


@celery_app.task(name="app.cv_tailoring.tasks.reconcile_stale_cv_extractions")
def reconcile_stale_cv_extractions() -> int:
    settings = get_settings()
    with SessionLocal() as db:
        stale_ids = find_stale_cv_versions(db)
        retry_ids: list[str] = []
        for version_id in stale_ids:
            version = db.get(CvVersion, version_id)
            if not version:
                continue
            if version.attempt_count < settings.cv_extraction_max_attempts:
                version.status = CvVersionStatus.uploaded
                version.processing_lease_expires_at = None
                retry_ids.append(str(version.id))
                emit_event("cv_extraction_requeued", cv_version_id=version.id, attempt=version.attempt_count)
            else:
                version.status = CvVersionStatus.failed
                version.failure_code = "extraction_lease_expired"
                version.processing_lease_expires_at = None
                emit_event("cv_extraction_failed", cv_version_id=version.id, code="extraction_lease_expired")
        db.commit()
    for version_id in retry_ids:
        extract_cv_version.delay(version_id)
    return len(retry_ids)
