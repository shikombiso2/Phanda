from __future__ import annotations

from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.models import CvVersion, CvVersionStatus, Profile, utcnow
from app.core.storage import get_bytes, put_bytes
from app.cv_tailoring.extraction import CvExtractionError, extract_cv
from app.cv_tailoring.service import TransientTailoringError, fail_stale_documents, process_tailored_document


@celery_app.task(name="app.cv_tailoring.tasks.extract_cv_version")
def extract_cv_version(cv_version_id: str) -> None:
    with SessionLocal() as db:
        version = db.get(CvVersion, cv_version_id)
        if not version or version.status in {CvVersionStatus.ready, CvVersionStatus.failed}:
            return
        version.status = CvVersionStatus.extracting
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
            profile = db.get(Profile, version.user_id)
            active = db.get(CvVersion, profile.active_cv_version_id) if profile and profile.active_cv_version_id else None
            if profile and (not active or version.version_number >= active.version_number):
                profile.active_cv_version_id = version.id
            db.commit()
        except CvExtractionError as exc:
            version = db.get(CvVersion, cv_version_id)
            if version:
                version.status = CvVersionStatus.failed
                version.failure_code = exc.code
                db.commit()
        except Exception:
            version = db.get(CvVersion, cv_version_id)
            if version:
                version.status = CvVersionStatus.failed
                version.failure_code = "extraction_failed"
                db.commit()


@celery_app.task(bind=True, name="app.cv_tailoring.tasks.process_tailored_document", max_retries=2)
def process_tailored_document_task(self, document_id: str) -> None:
    try:
        with SessionLocal() as db:
            process_tailored_document(db, document_id)
    except TransientTailoringError as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(name="app.cv_tailoring.tasks.reconcile_stale_tailoring")
def reconcile_stale_tailoring() -> int:
    with SessionLocal() as db:
        retry_ids = fail_stale_documents(db)
    for document_id in retry_ids:
        process_tailored_document_task.delay(document_id)
    return len(retry_ids)
