"""Full HTTP-level auth flow against real PostgreSQL.

Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set — same
convention as tests/test_postgres_tailoring_integration.py, and for the same
reason: this exercises real row locking, unique constraints, and constraint
violations (duplicate email) that a mocked session cannot meaningfully
stand in for.
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.app_factory import create_app
from app.auth.google import VerifiedGoogleIdentity
from app.core.config import get_settings
from app.core.db import get_db
from app.core.models import Profile, RefreshToken, User, UserAuthIdentity
from app.core.security import hash_refresh_token
from tests.postgres_harness import PostgresHarness


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class AuthFlowIntegrationTests(unittest.TestCase):
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
        cls.redis = redis.from_url(get_settings().redis_url)

    def setUp(self):
        # check_rate_limit (app/core/rate_limit.py) keys against real Redis,
        # which -- unlike PostgresHarness's disposable database -- is not
        # fresh per test run. Without this, a real 429 from an earlier test
        # or an earlier run of this same suite masks whatever this test is
        # actually trying to verify (confirmed: this is what "429 != 201"
        # and its cascading "the user was never created" failures were).
        for pattern in ("ratelimit:register:*", "ratelimit:login:*", "ratelimit:google:*", "ratelimit:refresh:*"):
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)

    @classmethod
    def tearDownClass(cls):
        cls.app.dependency_overrides.clear()
        cls.client.close()
        cls.redis.close()
        cls.engine.dispose()
        cls.harness.drop()

    def _unique_email(self) -> str:
        # example.com, not example.test: email-validator (which backs
        # pydantic's EmailStr, used by RegisterIn/LoginIn) correctly rejects
        # .test as a reserved, non-deliverable TLD -- verified directly
        # against a real request. example.com is RFC 2606 reserved
        # specifically for documentation/testing and is accepted.
        return f"user-{uuid.uuid4().hex[:12]}@example.com"

    def test_register_creates_user_and_profile_and_returns_tokens(self):
        email = self._unique_email()
        response = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["is_new_user"])
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)

        with self.Session() as db:
            user = db.scalar(select(User).where(User.email == email))
            self.assertIsNotNone(user)
            self.assertNotEqual(user.password_hash, "Correct-Horse-1")
            self.assertIsNotNone(db.get(Profile, user.id))

    def test_registration_rejects_mismatched_confirmation(self):
        response = self.client.post(
            "/auth/register", json={"email": self._unique_email(), "password": "Correct-Horse-1", "confirm_password": "different"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_duplicate_email_registration_is_rejected(self):
        email = self._unique_email()
        self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})

        response = self.client.post("/auth/register", json={"email": email, "password": "Another-Password-2", "confirm_password": "Another-Password-2"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "email_already_registered")

    def test_login_with_correct_credentials_succeeds(self):
        email = self._unique_email()
        self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})

        response = self.client.post("/auth/login", json={"email": email, "password": "Correct-Horse-1"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_new_user"])

    def test_wrong_password_and_unknown_email_fail_identically(self):
        email = self._unique_email()
        self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})

        wrong_password = self.client.post("/auth/login", json={"email": email, "password": "totally-wrong"})
        unknown_email = self.client.post("/auth/login", json={"email": self._unique_email(), "password": "totally-wrong"})

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(wrong_password.json()["code"], "invalid_credentials")
        self.assertEqual(wrong_password.json(), unknown_email.json())

    def _age_revocation_past_grace(self, refresh_token: str) -> None:
        """Backdate a token's revoked_at so it falls outside the grace window."""
        settings = get_settings()
        with self.Session() as db:
            token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_token)))
            token.revoked_at = datetime.now(timezone.utc) - timedelta(seconds=settings.refresh_reuse_grace_seconds + 5)
            db.commit()

    def test_concurrent_refresh_inside_grace_window_does_not_kill_the_session(self):
        """Two in-flight requests refreshing with the same token -- what a real
        Android client does when parallel calls 401 together -- must both
        succeed and must not revoke the user's other sessions."""
        email = self._unique_email()
        register = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
        shared_refresh = register.json()["refresh_token"]
        other_session = self.client.post("/auth/login", json={"email": email, "password": "Correct-Horse-1"})
        other_session_refresh = other_session.json()["refresh_token"]

        first = self.client.post("/auth/token/refresh", json={"refresh_token": shared_refresh})
        second = self.client.post("/auth/token/refresh", json={"refresh_token": shared_refresh})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200, "a racing second refresh inside the grace window must not be treated as theft")
        self.assertNotEqual(first.json()["refresh_token"], second.json()["refresh_token"])

        # The unrelated session on another device must be untouched, and both
        # tokens handed out above must themselves still rotate normally.
        self.assertEqual(self.client.post("/auth/token/refresh", json={"refresh_token": other_session_refresh}).status_code, 200)
        self.assertEqual(self.client.post("/auth/token/refresh", json={"refresh_token": second.json()["refresh_token"]}).status_code, 200)

    def test_reuse_after_the_grace_window_still_revokes_every_session(self):
        """The grace window must not blunt real theft detection: the same reuse,
        once the window has passed, still kills the whole user's sessions."""
        email = self._unique_email()
        register = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
        stolen_refresh = register.json()["refresh_token"]
        other_session = self.client.post("/auth/login", json={"email": email, "password": "Correct-Horse-1"})
        other_session_refresh = other_session.json()["refresh_token"]

        rotated = self.client.post("/auth/token/refresh", json={"refresh_token": stolen_refresh})
        self.assertEqual(rotated.status_code, 200)
        self._age_revocation_past_grace(stolen_refresh)

        reuse = self.client.post("/auth/token/refresh", json={"refresh_token": stolen_refresh})

        self.assertEqual(reuse.status_code, 401)
        self.assertEqual(reuse.json()["code"], "invalid_refresh_token")
        self.assertEqual(self.client.post("/auth/token/refresh", json={"refresh_token": rotated.json()["refresh_token"]}).status_code, 401)
        self.assertEqual(self.client.post("/auth/token/refresh", json={"refresh_token": other_session_refresh}).status_code, 401)

    def test_refresh_rotates_and_the_old_token_stops_working(self):
        email = self._unique_email()
        register = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
        old_refresh = register.json()["refresh_token"]

        first_refresh = self.client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
        self.assertEqual(first_refresh.status_code, 200)
        new_refresh_token = first_refresh.json()["refresh_token"]
        self.assertNotEqual(new_refresh_token, old_refresh)

        # Push the reuse outside the concurrent-refresh grace window. Before
        # that window existed this test's reuse was immediate; now an immediate
        # second presentation is a benign racing client by design, so the
        # precondition this test always meant -- "this reuse is not a race" --
        # has to be stated explicitly rather than assumed from timing.
        self._age_revocation_past_grace(old_refresh)

        reuse_attempt = self.client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
        self.assertEqual(reuse_attempt.status_code, 401)

        still_valid = self.client.post("/auth/token/refresh", json={"refresh_token": new_refresh_token})
        # Reuse of the rotated-away token must have revoked the whole chain,
        # including the token that replaced it — otherwise a stolen token
        # only costs the attacker one refresh instead of the whole session.
        self.assertEqual(still_valid.status_code, 401)

    def test_logout_revokes_the_presented_refresh_token(self):
        email = self._unique_email()
        register = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
        refresh_token = register.json()["refresh_token"]

        logout = self.client.post("/auth/logout", json={"refresh_token": refresh_token})
        self.assertEqual(logout.status_code, 204)

        reuse = self.client.post("/auth/token/refresh", json={"refresh_token": refresh_token})
        self.assertEqual(reuse.status_code, 401)

    def test_logout_all_revokes_every_session_for_the_user(self):
        email = self._unique_email()
        register = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
        access_token = register.json()["access_token"]
        refresh_token = register.json()["refresh_token"]
        second_login = self.client.post("/auth/login", json={"email": email, "password": "Correct-Horse-1"})
        second_refresh_token = second_login.json()["refresh_token"]

        logout_all = self.client.post("/auth/logout-all", headers={"Authorization": f"Bearer {access_token}"})
        self.assertEqual(logout_all.status_code, 204)

        self.assertEqual(self.client.post("/auth/token/refresh", json={"refresh_token": refresh_token}).status_code, 401)
        self.assertEqual(self.client.post("/auth/token/refresh", json={"refresh_token": second_refresh_token}).status_code, 401)

    def test_rate_limiting_is_enforced_by_real_redis(self):
        """Exhausts the real per-IP register limit (10/hour) against the
        actual Redis container -- not a mock -- and confirms the 11th
        request is rejected with a Retry-After header, and that requests
        under the limit are unaffected."""
        responses = [
            self.client.post("/auth/register", json={"email": self._unique_email(), "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
            for _ in range(10)
        ]
        self.assertTrue(all(r.status_code == 201 for r in responses), [r.status_code for r in responses])

        limited = self.client.post("/auth/register", json={"email": self._unique_email(), "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})

        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["code"], "rate_limited")
        self.assertIn("Retry-After", limited.headers)

    @patch("app.auth.router.verify_google_id_token")
    def test_google_signup_creates_a_new_user(self, verify):
        email = self._unique_email()
        verify.return_value = VerifiedGoogleIdentity(subject="google-subject-1", email=email, email_verified=True)

        response = self.client.post("/auth/google", json={"id_token": "opaque-token"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_new_user"])
        with self.Session() as db:
            user = db.scalar(select(User).where(User.email == email))
            self.assertIsNotNone(user)
            self.assertIsNone(user.password_hash)
            link = db.scalar(select(UserAuthIdentity).where(UserAuthIdentity.provider_subject == "google-subject-1"))
            self.assertEqual(link.user_id, user.id)

    @patch("app.auth.router.verify_google_id_token")
    def test_google_login_links_to_an_existing_password_account_without_duplicating_it(self, verify):
        email = self._unique_email()
        register = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
        with self.Session() as db:
            original_user_id = db.scalar(select(User).where(User.email == email)).id

        verify.return_value = VerifiedGoogleIdentity(subject="google-subject-2", email=email, email_verified=True)
        response = self.client.post("/auth/google", json={"id_token": "opaque-token"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_new_user"])
        with self.Session() as db:
            matching_users = db.scalars(select(User).where(User.email == email)).all()
            self.assertEqual(len(matching_users), 1, "Google sign-in must link, not duplicate, an existing account")
            self.assertEqual(matching_users[0].id, original_user_id)

    @patch("app.auth.router.verify_google_id_token")
    def test_second_google_login_reuses_the_linked_identity(self, verify):
        email = self._unique_email()
        verify.return_value = VerifiedGoogleIdentity(subject="google-subject-3", email=email, email_verified=True)
        first = self.client.post("/auth/google", json={"id_token": "token-1"})
        second = self.client.post("/auth/google", json={"id_token": "token-2"})

        self.assertTrue(first.json()["is_new_user"])
        self.assertFalse(second.json()["is_new_user"])
        with self.Session() as db:
            identities = db.scalars(select(UserAuthIdentity).where(UserAuthIdentity.provider_subject == "google-subject-3")).all()
            self.assertEqual(len(identities), 1)


if __name__ == "__main__":
    unittest.main()
