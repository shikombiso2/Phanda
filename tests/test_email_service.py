import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.core.config import get_settings
from app.core.email import EmailAttachment, EmailOutcomeUnknown, send_email


class SendEmailTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.original_provider = self.settings.email_provider
        self.original_sendgrid_key = self.settings.sendgrid_api_key
        self.original_mailgun_key = self.settings.mailgun_api_key
        self.original_mailgun_domain = self.settings.mailgun_domain

    def tearDown(self):
        self.settings.email_provider = self.original_provider
        self.settings.sendgrid_api_key = self.original_sendgrid_key
        self.settings.mailgun_api_key = self.original_mailgun_key
        self.settings.mailgun_domain = self.original_mailgun_domain

    def test_no_provider_configured_raises(self):
        self.settings.email_provider = "sendgrid"
        self.settings.sendgrid_api_key = None
        with self.assertRaises(RuntimeError):
            asyncio.run(send_email(to="a@example.test", subject="s", text="t"))

    @patch("app.core.email.httpx.AsyncClient")
    def test_sendgrid_reply_to_and_attachments_are_included(self, client_class):
        self.settings.email_provider = "sendgrid"
        self.settings.sendgrid_api_key = "key"
        client = AsyncMock()
        client.post.return_value = Mock(status_code=202)
        client_class.return_value.__aenter__.return_value = client

        asyncio.run(send_email(
            to="employer@example.test", subject="Hi", text="body", reply_to="candidate@example.test",
            attachments=[EmailAttachment(filename="cv.pdf", content=b"pdf-bytes")],
        ))

        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["reply_to"], {"email": "candidate@example.test"})
        self.assertEqual(payload["attachments"][0]["filename"], "cv.pdf")

    @patch("app.core.email.httpx.AsyncClient")
    def test_sendgrid_5xx_is_unknown_outcome_not_a_hard_failure(self, client_class):
        self.settings.email_provider = "sendgrid"
        self.settings.sendgrid_api_key = "key"
        client = AsyncMock()
        client.post.return_value = Mock(status_code=500)
        client_class.return_value.__aenter__.return_value = client

        with self.assertRaises(EmailOutcomeUnknown):
            asyncio.run(send_email(to="a@example.test", subject="s", text="t"))

    @patch("app.core.email.httpx.AsyncClient")
    def test_mailgun_reply_to_header_is_sent(self, client_class):
        self.settings.email_provider = "mailgun"
        self.settings.mailgun_api_key = "key"
        self.settings.mailgun_domain = "mg.phanda.example"
        client = AsyncMock()
        client.post.return_value = Mock(status_code=200)
        client_class.return_value.__aenter__.return_value = client

        asyncio.run(send_email(to="employer@example.test", subject="Hi", text="body", reply_to="candidate@example.test"))

        data = client.post.call_args.kwargs["data"]
        self.assertEqual(data["h:Reply-To"], "candidate@example.test")


if __name__ == "__main__":
    unittest.main()
