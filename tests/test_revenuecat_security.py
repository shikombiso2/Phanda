import unittest
import uuid
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import get_settings
from app.monetization.revenuecat_webhook import _extract_balance, _resolve_user_id, _verify_signature


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


class ResolveUserIdTests(unittest.TestCase):
    """Regression coverage for a verified crash: `aliases: []` (present but
    empty) used to raise IndexError, turning a webhook into a 500 that
    RevenueCat would retry indefinitely."""

    def test_empty_aliases_list_does_not_raise(self):
        self.assertIsNone(_resolve_user_id({"aliases": []}))

    def test_missing_aliases_key_does_not_raise(self):
        self.assertIsNone(_resolve_user_id({}))

    def test_app_user_id_takes_precedence_over_aliases(self):
        user_id = uuid.uuid4()
        self.assertEqual(_resolve_user_id({"app_user_id": str(user_id), "aliases": [str(uuid.uuid4())]}), user_id)

    def test_falls_back_to_first_alias_when_app_user_id_absent(self):
        user_id = uuid.uuid4()
        self.assertEqual(_resolve_user_id({"aliases": [str(user_id)]}), user_id)


class ExtractBalanceTests(unittest.TestCase):
    """A malformed or ambiguous event must not be interpreted as balance=0 --
    that would silently zero a real, previously-granted wallet balance."""

    def test_no_recognizable_balance_field_returns_none_not_zero(self):
        self.assertIsNone(_extract_balance({"currency": "boost_tokens"}))

    def test_non_numeric_balance_returns_none(self):
        self.assertIsNone(_extract_balance({"balance": "not-a-number"}))

    def test_balance_field_is_used_when_present(self):
        self.assertEqual(_extract_balance({"balance": 5}), 5)

    def test_negative_amount_is_floored_at_zero(self):
        self.assertEqual(_extract_balance({"amount": -3}), 0)
