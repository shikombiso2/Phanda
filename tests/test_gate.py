import unittest
import uuid
from datetime import date
from unittest.mock import patch

from app.core.models import Entitlement, FeatureUsage, Wallet
from app.monetization.gate import check_access, monthly_period_start


class FakeScalarResult:
    def __init__(self, values):
        self.values = list(values)

    def scalar(self):
        return self.values.pop(0) if self.values else None


class FakeDb:
    def __init__(self, scalars):
        self.result = FakeScalarResult(scalars)
        self.added = []
        self.commits = 0

    def scalar(self, _query):
        return self.result.scalar()

    def add(self, value):
        self.added.append(value)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1


class GateTests(unittest.TestCase):
    def test_monthly_period_start(self):
        self.assertEqual(monthly_period_start(date(2026, 8, 30)), date(2026, 8, 1))

    def test_premium_allows_without_incrementing_usage(self):
        user_id = uuid.uuid4()
        db = FakeDb([Entitlement(user_id=user_id, is_active=True, revenuecat_customer_id="rc")])

        decision = check_access(db, user_id, "cv_tailor")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "premium")
        self.assertEqual(db.commits, 0)

    def test_free_quota_allows_and_increments(self):
        user_id = uuid.uuid4()
        usage = FeatureUsage(user_id=user_id, feature_key="cv_tailor", period_start=date(2026, 8, 1), free_uses_count=1)
        db = FakeDb([None, usage])

        decision = check_access(db, user_id, "cv_tailor")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "free_quota")
        self.assertEqual(usage.free_uses_count, 2)
        self.assertEqual(db.commits, 1)

    @patch("app.monetization.gate.date")
    def test_boost_token_spends_once_per_day(self, mocked_date):
        mocked_date.today.return_value = date(2026, 8, 30)
        user_id = uuid.uuid4()
        usage = FeatureUsage(user_id=user_id, feature_key="cv_tailor", period_start=date(2026, 8, 1), free_uses_count=3)
        wallet = Wallet(user_id=user_id, balance=2)
        db = FakeDb([None, usage, wallet])

        decision = check_access(db, user_id, "cv_tailor")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "boost_token")
        self.assertEqual(wallet.balance, 1)
        self.assertEqual(usage.ad_reward_date, date(2026, 8, 30))


if __name__ == "__main__":
    unittest.main()

