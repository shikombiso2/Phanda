import unittest
import uuid
from datetime import date
from unittest.mock import patch

from app.core.models import Entitlement, FeatureUsage, Wallet
from app.monetization.gate import TailoringAllowance, check_access, monthly_period_start


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

    @patch("app.monetization.gate.get_tailoring_allowance")
    def test_tailoring_gate_is_read_only_for_premium(self, mocked_allowance):
        user_id = uuid.uuid4()
        db = FakeDb([])
        mocked_allowance.return_value = TailoringAllowance(0, 0, True, 100, False, False)

        decision = check_access(db, user_id, "cv_tailor")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "tailoring_reservation_required")
        self.assertEqual(db.commits, 0)

    @patch("app.monetization.gate.get_tailoring_allowance")
    def test_tailoring_gate_does_not_increment_free_usage(self, mocked_allowance):
        user_id = uuid.uuid4()
        usage = FeatureUsage(user_id=user_id, feature_key="cv_tailor", period_start=date(2026, 8, 1), free_uses_count=1)
        db = FakeDb([])
        mocked_allowance.return_value = TailoringAllowance(2, 0, False, None, False, False)

        decision = check_access(db, user_id, "cv_tailor")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "tailoring_reservation_required")
        self.assertEqual(usage.free_uses_count, 1)
        self.assertEqual(db.commits, 0)

    @patch("app.monetization.gate.get_tailoring_allowance")
    def test_tailoring_gate_does_not_spend_boost_tokens(self, mocked_allowance):
        user_id = uuid.uuid4()
        usage = FeatureUsage(user_id=user_id, feature_key="cv_tailor", period_start=date(2026, 8, 1), free_uses_count=3)
        wallet = Wallet(user_id=user_id, balance=2)
        db = FakeDb([])
        mocked_allowance.return_value = TailoringAllowance(0, 0, False, None, True, True)

        decision = check_access(db, user_id, "cv_tailor")

        self.assertFalse(decision.allowed)
        self.assertEqual(wallet.balance, 2)


if __name__ == "__main__":
    unittest.main()
