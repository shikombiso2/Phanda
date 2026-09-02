"""Full RevenueCat webhook flow against real PostgreSQL.

Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set -- same
convention as the other *_postgres_integration.py files. Signature
verification itself is exercised end-to-end here (not mocked) since it is
the entire trust boundary for this endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.app_factory import create_app
from app.core.config import get_settings
from app.core.db import get_db
from app.core.models import Entitlement, RewardEvent, User, Wallet
from app.monetization.gate import BOOST_CURRENCY, TAILORING_CURRENCY
from tests.postgres_harness import PostgresHarness

WEBHOOK_SECRET = "test-revenuecat-secret"


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class RevenueCatWebhookIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = PostgresHarness()
        cls.harness.create()
        cls.engine = create_engine(cls.harness.test_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.app = create_app()

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        cls.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(cls.app)
        cls.settings = get_settings()
        cls.original_secret = cls.settings.revenuecat_webhook_secret
        cls.settings.revenuecat_webhook_secret = WEBHOOK_SECRET

    @classmethod
    def tearDownClass(cls):
        cls.settings.revenuecat_webhook_secret = cls.original_secret
        cls.app.dependency_overrides.clear()
        cls.client.close()
        cls.engine.dispose()
        cls.harness.drop()

    def setUp(self):
        with self.Session() as db:
            user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            db.add(user)
            db.commit()
            self.user_id = user.id

    def _post(self, event: dict) -> "httpx.Response":  # noqa: F821 (typing convenience only)
        body = json.dumps({"event": event}).encode()
        timestamp = str(int(time.time()))
        signed = f"{timestamp}.".encode() + body
        signature = hmac.new(WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
        return self.client.post(
            "/webhooks/revenuecat",
            content=body,
            headers={"content-type": "application/json", "X-RevenueCat-Webhook-Signature": f"t={timestamp},v1={signature}"},
        )

    def test_initial_purchase_grants_premium_entitlement(self):
        response = self._post({"type": "INITIAL_PURCHASE", "app_user_id": str(self.user_id)})
        self.assertEqual(response.status_code, 200)
        with self.Session() as db:
            entitlement = db.scalar(select(Entitlement).where(Entitlement.user_id == self.user_id))
            self.assertTrue(entitlement.is_active)

    def test_cancellation_deactivates_a_previously_active_entitlement(self):
        self._post({"type": "INITIAL_PURCHASE", "app_user_id": str(self.user_id)})
        response = self._post({"type": "CANCELLATION", "app_user_id": str(self.user_id)})
        self.assertEqual(response.status_code, 200)
        with self.Session() as db:
            entitlement = db.scalar(select(Entitlement).where(Entitlement.user_id == self.user_id))
            self.assertFalse(entitlement.is_active)

    def test_tailoring_reward_is_granted_exactly_once_when_the_same_event_is_delivered_twice(self):
        event = {"type": "VIRTUAL_CURRENCY_TRANSACTION", "app_user_id": str(self.user_id), "currency": TAILORING_CURRENCY, "id": "evt-replay-1"}

        first = self._post(event)
        second = self._post(event)  # RevenueCat (or any webhook sender) may redeliver.

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id, Wallet.currency_key == TAILORING_CURRENCY))
            self.assertEqual(wallet.balance, 1, "a replayed reward event must not grant credits twice")
            events = db.scalars(select(RewardEvent).where(RewardEvent.external_event_id == "evt-replay-1")).all()
            self.assertEqual(len(events), 1)

    def test_virtual_currency_balance_changed_sets_the_boost_wallet(self):
        response = self._post({"type": "VIRTUAL_CURRENCY_BALANCE_CHANGED", "app_user_id": str(self.user_id), "currency": BOOST_CURRENCY, "balance": 7})
        self.assertEqual(response.status_code, 200)
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id, Wallet.currency_key == BOOST_CURRENCY))
            self.assertEqual(wallet.balance, 7)

    def test_malformed_balance_does_not_zero_an_existing_wallet(self):
        self._post({"type": "VIRTUAL_CURRENCY_BALANCE_CHANGED", "app_user_id": str(self.user_id), "currency": BOOST_CURRENCY, "balance": 7})

        malformed = self._post({"type": "VIRTUAL_CURRENCY_BALANCE_CHANGED", "app_user_id": str(self.user_id), "currency": BOOST_CURRENCY})

        self.assertEqual(malformed.status_code, 200)
        with self.Session() as db:
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id, Wallet.currency_key == BOOST_CURRENCY))
            self.assertEqual(wallet.balance, 7, "a balance-less event must be ignored, not treated as balance=0")

    def test_empty_aliases_list_is_ignored_rather_than_crashing(self):
        response = self._post({"type": "INITIAL_PURCHASE", "aliases": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")

    def test_invalid_signature_is_rejected(self):
        body = json.dumps({"event": {"type": "INITIAL_PURCHASE", "app_user_id": str(self.user_id)}}).encode()
        response = self.client.post(
            "/webhooks/revenuecat", content=body,
            headers={"content-type": "application/json", "X-RevenueCat-Webhook-Signature": "t=1,v1=deadbeef"},
        )
        self.assertEqual(response.status_code, 401)
        with self.Session() as db:
            self.assertIsNone(db.scalar(select(Entitlement).where(Entitlement.user_id == self.user_id)))


if __name__ == "__main__":
    unittest.main()
