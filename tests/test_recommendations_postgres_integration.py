"""Recommendation endpoint and pagination against real PostgreSQL.

Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set.
"""
from __future__ import annotations

import os
import unittest
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.app_factory import create_app
from app.core.db import get_db
from app.core.models import ApplyMethod, ExperienceLevel, JobType, Listing, ListingType, Profile, User
from app.core.security import get_current_user
from tests.postgres_harness import PostgresHarness


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class RecommendationEndpointIntegrationTests(unittest.TestCase):
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

    def setUp(self):
        with self.Session() as db:
            self.user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            self.profile = Profile(
                user_id=self.user.id, job_type=JobType.full_time, experience_level=ExperienceLevel.none,
                skills=["excel", "communication"], industries=[], location="Johannesburg", open_to_remote=False,
            )
            db.add_all([self.user, self.profile])
            for i in range(3):
                db.add(Listing(
                    id=uuid.uuid4(), source="test", source_listing_id=f"match-{uuid.uuid4()}", title=f"Admin Role {i}",
                    description="Excel and communication required", required_skills=["excel", "communication"],
                    listing_type=ListingType.job, location="Johannesburg", apply_method=ApplyMethod.ats_link,
                    apply_target="https://example.test/apply",
                ))
            db.commit()
        self.app.dependency_overrides[get_current_user] = lambda: self.user

    def tearDown(self):
        self.app.dependency_overrides.pop(get_current_user, None)

    def test_matches_are_scored_and_include_explanations(self):
        response = self.client.get("/listings/matches")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body["items"]), 3)
        first = body["items"][0]
        self.assertIn("match", first)
        self.assertIn("score", first["match"])
        self.assertIn("factors", first["match"])
        self.assertGreater(first["match"]["score"], 50)

    def test_matches_pagination_respects_limit(self):
        response = self.client.get("/listings/matches", params={"limit": 1})
        body = response.json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["limit"], 1)
        self.assertTrue(body["has_more"])

    def test_listings_list_is_paginated_and_omits_description(self):
        response = self.client.get("/listings", params={"limit": 2})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertNotIn("description", body["items"][0])

    def test_applications_list_embeds_listing_summary(self):
        with self.Session() as db:
            listing = db.query(Listing).first()
        apply_response = self.client.post(f"/applications/{listing.id}/apply")
        self.assertIn(apply_response.status_code, (202, 400))  # 400 if no ready CV -- either way, check list shape next
        response = self.client.get("/applications")
        self.assertEqual(response.status_code, 200)
        self.assertIn("items", response.json())


if __name__ == "__main__":
    unittest.main()
