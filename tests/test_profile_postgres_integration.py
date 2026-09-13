"""Profile update against real PostgreSQL.

Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set -- same
convention as the other *_postgres_integration.py files.
"""
from __future__ import annotations

import os
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.app_factory import create_app
from app.core.db import get_db
from app.core.models import User
from tests.postgres_harness import PostgresHarness


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class ProfileUpdateIntegrationTests(unittest.TestCase):
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
        return f"user-{uuid.uuid4().hex[:12]}@example.com"

    def test_put_profile_without_email_field_succeeds_and_leaves_email_unchanged(self):
        email = self._unique_email()
        register = self.client.post(
            "/auth/register", json={"email": email, "password": "Correct-Horse-1", "confirm_password": "Correct-Horse-1"}
        )
        access_token = register.json()["access_token"]

        response = self.client.put(
            "/profile",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"location": "Cape Town", "skills": ["python"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], email)
        with self.Session() as db:
            user = db.scalar(select(User).where(User.email == email))
            self.assertEqual(user.email, email)


if __name__ == "__main__":
    unittest.main()
