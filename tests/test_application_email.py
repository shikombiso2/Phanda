import asyncio
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app.applications.email import EmailOutcomeUnknown, send_application_email
from app.applications.tasks import send_application_email_task
from app.core.config import get_settings
from app.core.models import Application, ApplicationSubmissionStatus, CvVersion, Listing, Profile, User


class FakeSession:
    def __init__(self, objects):
        self.objects = objects
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def get(self, model, _identifier):
        return self.objects.get(model)

    def commit(self):
        self.commits += 1


class EmailOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.original_provider = self.settings.email_provider
        self.original_key = self.settings.sendgrid_api_key
        self.settings.email_provider = "sendgrid"
        self.settings.sendgrid_api_key = "key"

    def tearDown(self):
        self.settings.email_provider = self.original_provider
        self.settings.sendgrid_api_key = self.original_key

    @patch("app.core.email.httpx.AsyncClient")
    def test_timeout_is_unknown_not_safe_to_resend(self, client_class):
        client = AsyncMock()
        client.post.side_effect = httpx.TimeoutException("timeout")
        client_class.return_value.__aenter__.return_value = client
        with self.assertRaises(EmailOutcomeUnknown):
            asyncio.run(send_application_email(
                to_email="employer@example.test", subject="Application", body="Attached", cv_bytes=b"pdf", cv_filename="cv.pdf"
            ))

    @patch("app.core.email.httpx.AsyncClient")
    def test_attachment_bytes_are_sent_without_storage_uri(self, client_class):
        client = AsyncMock()
        response = Mock(status_code=202)
        client.post.return_value = response
        client_class.return_value.__aenter__.return_value = client
        asyncio.run(send_application_email(
            to_email="employer@example.test", subject="Application", body="Attached", cv_bytes=b"pdf", cv_filename="cv.pdf"
        ))
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["attachments"][0]["filename"], "cv.pdf")
        self.assertNotIn("s3://", str(payload))
        self.assertNotIn("local://", str(payload))

    @patch("app.applications.tasks.render_master_cv_pdf", return_value=b"%PDF-master")
    @patch("app.applications.tasks.get_bytes", return_value=b"Master CV extracted text")
    @patch("app.applications.tasks.send_application_email", new_callable=AsyncMock)
    @patch("app.applications.tasks.SessionLocal")
    def test_docx_master_cv_is_rendered_before_emailing(self, session_local, send_email, get_bytes, render_pdf):
        user_id = uuid.uuid4()
        application = SimpleNamespace(
            id=uuid.uuid4(), user_id=user_id, listing_id=uuid.uuid4(), tailored_document_id=None,
            submission_status=ApplicationSubmissionStatus.email_queued, email_attempt_count=0,
        )
        listing = SimpleNamespace(apply_target="employer@example.test", title="Developer")
        version = SimpleNamespace(
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            storage_key="users/u1/original.docx", extracted_text_key="users/u1/extracted.txt",
        )
        profile = SimpleNamespace(active_cv_version_id=uuid.uuid4())
        user = SimpleNamespace(email="candidate@example.test")
        session = FakeSession({
            Application: application,
            Listing: listing,
            Profile: profile,
            CvVersion: version,
            User: user,
        })
        session_local.return_value = session

        send_application_email_task.run(str(application.id))

        render_pdf.assert_called_once_with(b"Master CV extracted text".decode("utf-8"))
        self.assertEqual(send_email.await_args.kwargs["cv_bytes"], b"%PDF-master")
        self.assertEqual(send_email.await_args.kwargs["cv_filename"], "Phanda_CV_Developer.pdf")
        self.assertEqual(send_email.await_args.kwargs["reply_to"], "candidate@example.test")
        self.assertEqual(application.submission_status, ApplicationSubmissionStatus.email_sent)
        self.assertEqual(application.email_attempt_count, 1)
        self.assertEqual(session.commits, 1)
