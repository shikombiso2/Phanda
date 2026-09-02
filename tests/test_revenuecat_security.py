import unittest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import get_settings
from app.monetization.revenuecat_webhook import _verify_signature


class RevenueCatSecurityTests(unittest.TestCase):
    def test_signature_requires_expected_hmac(self):
        self.assertFalse(_verify_signature(b"{}", None, "secret"))
        self.assertFalse(_verify_signature(b"{}", "t=1,v1=not-valid", "secret"))

    def test_unconfigured_webhook_is_not_accepted(self):
        settings = get_settings()
        original = settings.revenuecat_webhook_secret
        settings.revenuecat_webhook_secret = None
        try:
            response = TestClient(create_app()).post("/webhooks/revenuecat", content=b"{}", headers={"content-type": "application/json"})
            self.assertEqual(response.status_code, 503)
        finally:
            settings.revenuecat_webhook_secret = original
