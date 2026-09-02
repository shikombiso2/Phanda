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
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.app_factory import create_app
from app.auth.google import VerifiedGoogleIdentity
from app.core.db import get_db
from app.core.models import Profile, RefreshToken, User, UserAuthIdentity
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

    @classmethod
    def tearDownClass(cls):
        cls.app.dependency_overrides.clear()
        cls.client.close()
        cls.engine.dispose()
        cls.harness.drop()

    def _unique_email(self) -> str:
        return f"user-{uuid.uuid4().hex[:12]}@example.test"

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

    def test_refresh_rotates_and_the_old_token_stops_working(self):
        email = self._unique_email()
        register = self.client.post("/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"})
        old_refresh = register.json()["refresh_token"]

        first_refresh = self.client.post("/auth/token/refresh", json={"refresh_token": old_refresh})
        self.assertEqual(first_refresh.status_code, 200)
        new_refresh_token = first_refresh.json()["refresh_token"]
        self.assertNotEqual(new_refresh_token, old_refresh)

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
