import asyncio

from app.applications.email import EmailOutcomeUnknown, send_application_email
from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.models import Application, ApplicationSubmissionStatus, CvVersion, Listing, Profile, TailoredDocument, User
from app.core.observability import emit_event
from app.core.storage import get_bytes
from app.cv_tailoring.renderer import render_master_cv_pdf


@celery_app.task(name="app.applications.tasks.send_application_email")
def send_application_email_task(application_id: str) -> None:
    """Do not retry automatically: an unknown provider result could duplicate an application."""
    with SessionLocal() as db:
        application = db.get(Application, application_id)
        if not application or application.submission_status != ApplicationSubmissionStatus.email_queued:
            return
        listing = db.get(Listing, application.listing_id)
        try:
            if application.tailored_document_id:
                document = db.get(TailoredDocument, application.tailored_document_id)
                cv_key = document.tailored_cv_key if document else None
                cover_key = document.cover_letter_key if document else None
            else:
                profile = db.get(Profile, application.user_id)
                version = db.get(CvVersion, profile.active_cv_version_id) if profile and profile.active_cv_version_id else None
                cv_key = version.storage_key if version and version.content_type == "application/pdf" else None
                cover_key = None
            user = db.get(User, application.user_id)
            if not listing or not listing.apply_target:
                raise RuntimeError("application_file_unavailable")
            if application.tailored_document_id:
                if not cv_key:
                    raise RuntimeError("application_file_unavailable")
                cv_bytes = get_bytes(cv_key)
            elif not version:
                raise RuntimeError("application_file_unavailable")
            elif cv_key:
                cv_bytes = get_bytes(cv_key)
            elif version.extracted_text_key:
                cv_bytes = render_master_cv_pdf(get_bytes(version.extracted_text_key).decode("utf-8"))
            else:
                raise RuntimeError("application_file_unavailable")
            candidate_name = (user.email or "A Phanda candidate") if user else "A Phanda candidate"
            body = (
                f"Please find {candidate_name}'s application documents attached for the {listing.title} role.\n\n"
                f"Sent via Phanda on behalf of {candidate_name}."
                + (f" Reply to this email to reach the candidate directly at {user.email}." if user and user.email else "")
            )
            asyncio.run(send_application_email(
                to_email=listing.apply_target,
                subject=f"Application: {listing.title}",
                body=body,
                cv_bytes=cv_bytes,
                cv_filename=f"Phanda_CV_{listing.title[:60].replace(' ', '_')}.pdf",
                cover_letter_bytes=get_bytes(cover_key) if cover_key else None,
                reply_to=user.email if user and user.email else None,
            ))
            application.submission_status = ApplicationSubmissionStatus.email_sent
            emit_event("email_sent", application_id=application.id)
        except EmailOutcomeUnknown:
            application.submission_status = ApplicationSubmissionStatus.email_unknown
            emit_event("email_failed", application_id=application.id, outcome="unknown")
        except Exception:
            application.submission_status = ApplicationSubmissionStatus.email_failed
            emit_event("email_failed", application_id=application.id, outcome="failed")
        application.email_attempt_count += 1
        db.commit()
