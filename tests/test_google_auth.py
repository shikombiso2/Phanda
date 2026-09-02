import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.auth.google import GoogleAuthNotConfigured, verify_google_id_token
from app.core.config import get_settings


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.original = self.settings.google_oauth_client_ids

    def tearDown(self):
        self.settings.google_oauth_client_ids = self.original

    def test_raises_when_not_configured(self):
        self.settings.google_oauth_client_ids = None
        with self.assertRaises(GoogleAuthNotConfigured):
            verify_google_id_token("some-token")

    @patch("app.auth.google.google_id_token.verify_oauth2_token")
    def test_valid_token_returns_verified_identity(self, verify):
        self.settings.google_oauth_client_ids = "android-client-id.apps.googleusercontent.com"
        verify.return_value = {
            "aud": "android-client-id.apps.googleusercontent.com",
            "sub": "1234567890",
            "email": "candidate@example.com",
            "email_verified": True,
        }
        identity = verify_google_id_token("a-valid-token")
        self.assertEqual(identity.subject, "1234567890")
        self.assertEqual(identity.email, "candidate@example.com")
        self.assertTrue(identity.email_verified)

    @patch("app.auth.google.google_id_token.verify_oauth2_token")
    def test_wrong_audience_is_rejected_even_with_a_valid_signature(self, verify):
        """The library's own audience check is bypassed (audience=None) so
        multiple client IDs can be accepted; this module's own manual
        allowlist check must be the thing that actually enforces it."""
        self.settings.google_oauth_client_ids = "android-client-id.apps.googleusercontent.com"
        verify.return_value = {
            "aud": "some-other-apps-client-id.apps.googleusercontent.com",
            "sub": "1234567890",
            "email": "candidate@example.com",
            "email_verified": True,
        }
        with self.assertRaises(HTTPException) as ctx:
            verify_google_id_token("a-token-for-a-different-app")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.auth.google.google_id_token.verify_oauth2_token")
    def test_invalid_signature_is_rejected(self, verify):
        self.settings.google_oauth_client_ids = "android-client-id.apps.googleusercontent.com"
        verify.side_effect = ValueError("Token used too early")
        with self.assertRaises(HTTPException) as ctx:
            verify_google_id_token("a-tampered-token")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.auth.google.google_id_token.verify_oauth2_token")
    def test_missing_email_claim_is_rejected(self, verify):
        self.settings.google_oauth_client_ids = "android-client-id.apps.googleusercontent.com"
        verify.return_value = {"aud": "android-client-id.apps.googleusercontent.com", "sub": "1234567890"}
        with self.assertRaises(HTTPException):
            verify_google_id_token("a-token-without-email")

    def test_multiple_configured_client_ids_are_all_accepted(self):
        self.settings.google_oauth_client_ids = "android-id.apps.googleusercontent.com, web-id.apps.googleusercontent.com"
        self.assertEqual(
            self.settings.google_client_id_list(),
            ["android-id.apps.googleusercontent.com", "web-id.apps.googleusercontent.com"],
        )


if __name__ == "__main__":
    unittest.main()
