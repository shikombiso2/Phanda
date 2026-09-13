from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.models import CvVersion, ReservationStatus, TailoredDocument, TailoredDocumentStatus, TailoringRequestReservation, utcnow
from app.core.observability import emit_event
from app.core.storage import get_bytes, put_bytes
from app.cv_tailoring.gemini import get_tailoring_provider
from app.cv_tailoring.provider import ProviderError
from app.cv_tailoring.renderer import render_cover_letter_pdf, render_cv_pdf
from app.cv_tailoring.schemas import AnalysisPlan
from app.cv_tailoring.validation import validate_analysis, validate_tailored_cv
from app.monetization.gate import consume_reservation, release_reservation


class TransientTailoringError(RuntimeError):
    def __init__(self, code: str, retry_after_seconds: float | None = None):
        super().__init__(code)
        self.retry_after_seconds = retry_after_seconds


def process_tailored_document(db: Session, document_id) -> None:
    """Run one idempotent generation attempt. The Celery task handles retries."""
    document = db.scalar(select(TailoredDocument).where(TailoredDocument.id == document_id).with_for_update())
    if not document or document.status in {TailoredDocumentStatus.ready, TailoredDocumentStatus.cancelled}:
        return
    if document.status not in {TailoredDocumentStatus.queued, TailoredDocumentStatus.processing}:
        return
    settings = get_settings()
    document.status = TailoredDocumentStatus.processing
    document.attempt_count += 1
    document.processing_lease_expires_at = utcnow() + timedelta(minutes=settings.tailoring_reservation_minutes)
    db.commit()
    emit_event("tailoring_started", document_id=document.id, attempt=document.attempt_count)

    try:
        cv_version = db.get(CvVersion, document.cv_version_id)
        if not cv_version or not cv_version.extracted_text_key or cv_version.status.value != "ready":
            raise ProviderError("cv_not_ready")
        provider = get_tailoring_provider()

        if document.analysis_plan_json:
            # A retry of this exact document (same listing + CV pairing) that
            # already produced a validated plan on a prior attempt -- most
            # often a Celery-level retry after generate/revise hit a
            # transient provider error downstream of analysis. Re-running
            # analyze_and_plan here would resend the full CV text and job
            # description for a result we already have and already
            # validated; skip straight to generate. gate.py clears this
            # field whenever a document is reused for a genuinely new
            # request (the listing snapshot may have changed since), so its
            # presence here specifically means "safe to reuse".
            plan = AnalysisPlan.model_validate(document.analysis_plan_json)
            emit_event("tailoring_plan_reused", document_id=document_id, attempt=document.attempt_count)
        else:
            candidate_text = get_bytes(cv_version.extracted_text_key).decode("utf-8")
            plan = asyncio.run(provider.analyze_and_plan(candidate_text, document.listing_snapshot_json))
            analysis_issues = validate_analysis(plan, candidate_text)
            if analysis_issues:
                emit_event("validation_failed", document_id=document_id, stage="analysis", issue_count=len(analysis_issues))
                raise ProviderError("invalid_candidate_analysis")
            cv_version.candidate_facts_json = plan.candidate_facts.model_dump(mode="json")
            document.analysis_plan_json = plan.model_dump(mode="json")
            db.commit()

        _transition(db, document.id, TailoredDocumentStatus.validating)
        draft = asyncio.run(provider.generate(plan.candidate_facts, plan.job_requirements, plan.strategy))
        requirement_ids = {requirement.id for requirement in plan.job_requirements.requirements}
        issues = validate_tailored_cv(draft, plan.candidate_facts.facts, requirement_ids)
        if issues:
            emit_event("validation_failed", document_id=document_id, stage="draft", issue_count=len(issues))
            document = db.scalar(select(TailoredDocument).where(TailoredDocument.id == document_id).with_for_update())
            if not document:
                return
            if document.correction_attempted:
                raise ProviderError("validation_failed")
            document.correction_attempted = True
            document.status = TailoredDocumentStatus.processing
            db.commit()
            emit_event("correction_attempt", document_id=document_id)
            draft = asyncio.run(provider.revise(plan.candidate_facts, plan.job_requirements, plan.strategy, draft, issues))
            _transition(db, document_id, TailoredDocumentStatus.validating)
            issues = validate_tailored_cv(draft, plan.candidate_facts.facts, requirement_ids)
            if issues:
                emit_event("validation_failed", document_id=document_id, stage="corrected_draft", issue_count=len(issues))
                raise ProviderError("validation_failed")

        _transition(db, document_id, TailoredDocumentStatus.rendering)
        cv_pdf = render_cv_pdf(draft)
        cover_pdf = render_cover_letter_pdf(draft)
        base_key = f"users/{document.user_id}/tailored-documents/{document.id}"
        cv_key = put_bytes(cv_pdf, f"{base_key}/tailored-cv.pdf", "application/pdf")
        cover_key = put_bytes(cover_pdf, f"{base_key}/cover-letter.pdf", "application/pdf")

        document = db.scalar(select(TailoredDocument).where(TailoredDocument.id == document_id).with_for_update())
        if not document or document.status == TailoredDocumentStatus.cancelled:
            return
        document.status = TailoredDocumentStatus.ready
        document.tailored_cv_key = cv_key
        document.cover_letter_key = cover_key
        document.provider_name = provider.name
        document.model_name = provider.model_name
        document.processing_lease_expires_at = None
        document.ready_at = utcnow()
        consume_reservation(db, document)
        db.commit()
        emit_event("tailoring_completed", document_id=document.id, attempt=document.attempt_count)
    except ProviderError as exc:
        _handle_failure(db, document_id, exc.code, exc.retryable)
        if exc.retryable and _attempts_remaining(db, document_id):
            raise TransientTailoringError(exc.code, exc.retry_after_seconds) from exc
    except Exception:
        _handle_failure(db, document_id, "generation_failed", retryable=False)


def fail_stale_documents(db: Session) -> list[str]:
    now = utcnow()
    documents = db.scalars(
        select(TailoredDocument).where(
            TailoredDocument.status.in_(
                [TailoredDocumentStatus.processing, TailoredDocumentStatus.validating, TailoredDocumentStatus.rendering]
            ),
            TailoredDocument.processing_lease_expires_at.is_not(None),
            TailoredDocument.processing_lease_expires_at < now,
        )
    ).all()
    retry_ids: list[str] = []
    for document in documents:
        if document.attempt_count < get_settings().tailoring_max_attempts:
            document.status = TailoredDocumentStatus.queued
            document.processing_lease_expires_at = None
            retry_ids.append(str(document.id))
            emit_event("tailoring_cancelled", document_id=document.id, reason="processing_lease_expired_requeued")
        else:
            document.status = TailoredDocumentStatus.failed
            document.failure_code = "processing_lease_expired"
            document.processing_lease_expires_at = None
            release_reservation(db, document)
            emit_event("reservation_released", document_id=document.id, reason="processing_lease_expired")
    expired_queued = db.scalars(
        select(TailoredDocument)
        .join(TailoringRequestReservation, TailoringRequestReservation.tailored_document_id == TailoredDocument.id)
        .where(
            TailoredDocument.status == TailoredDocumentStatus.queued,
            TailoringRequestReservation.status == ReservationStatus.reserved,
            TailoringRequestReservation.expires_at < now,
        )
    ).all()
    for document in expired_queued:
        document.status = TailoredDocumentStatus.failed
        document.failure_code = "queue_lease_expired"
        release_reservation(db, document)
        emit_event("reservation_released", document_id=document.id, reason="queue_lease_expired")
    db.commit()
    return retry_ids


def _transition(db: Session, document_id, status: TailoredDocumentStatus) -> None:
    document = db.scalar(select(TailoredDocument).where(TailoredDocument.id == document_id).with_for_update())
    if not document or document.status == TailoredDocumentStatus.cancelled:
        raise ProviderError("document_cancelled")
    document.status = status
    db.commit()


def _handle_failure(db: Session, document_id, code: str, retryable: bool) -> None:
    document = db.scalar(select(TailoredDocument).where(TailoredDocument.id == document_id).with_for_update())
    if not document or document.status in {TailoredDocumentStatus.ready, TailoredDocumentStatus.cancelled}:
        return
    if retryable and document.attempt_count < get_settings().tailoring_max_attempts:
        document.status = TailoredDocumentStatus.queued
        document.processing_lease_expires_at = None
        document.failure_code = code
        db.commit()
        emit_event("tailoring_failed", document_id=document.id, code=code, retryable=True)
        return
    document.status = TailoredDocumentStatus.failed
    document.failure_code = code
    document.processing_lease_expires_at = None
    release_reservation(db, document)
    db.commit()
    emit_event("tailoring_failed", document_id=document.id, code=code, retryable=False)
    emit_event("reservation_released", document_id=document.id, reason=code)


def _attempts_remaining(db: Session, document_id) -> bool:
    document = db.get(TailoredDocument, document_id)
    return bool(document and document.status == TailoredDocumentStatus.queued and document.attempt_count < get_settings().tailoring_max_attempts)
