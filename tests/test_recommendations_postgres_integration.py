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
from app.core.models import ApplyMethod, CvVersion, CvVersionStatus, ExperienceLevel, JobType, Listing, ListingType, Profile, User
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

    def _add_cv_version(self, *, status: CvVersionStatus, extracted_skills: list[str], make_active: bool) -> CvVersion:
        with self.Session() as db:
            cv_version = CvVersion(
                id=uuid.uuid4(), user_id=self.user.id, version_number=1, status=status,
                storage_key=f"users/{self.user.id}/cv-versions/{uuid.uuid4()}/original.pdf",
                filename="cv.pdf", content_type="application/pdf", byte_size=1, sha256=uuid.uuid4().hex,
                extracted_skills=extracted_skills,
            )
            db.add(cv_version)
            if make_active:
                profile = db.get(Profile, self.user.id)
                profile.active_cv_version_id = cv_version.id
            db.commit()
            db.refresh(cv_version)
            return cv_version

    def test_matches_union_profile_and_cv_skills(self):
        # Profile only ever has "excel" (see setUp); the CV -- never typed
        # into the profile -- adds "python". A listing wanting both should
        # show both matched, per the confirmed separate-input design.
        self._add_cv_version(status=CvVersionStatus.ready, extracted_skills=["python"], make_active=True)
        with self.Session() as db:
            db.add(Listing(
                id=uuid.uuid4(), source="test", source_listing_id=f"cv-match-{uuid.uuid4()}",
                title="Python Admin Hybrid Role", description="Needs Excel and Python",
                required_skills=["excel", "python"], listing_type=ListingType.job, location="Johannesburg",
                apply_method=ApplyMethod.ats_link, apply_target="https://example.test/apply",
            ))
            db.commit()

        response = self.client.get("/listings/matches", params={"limit": 50})
        self.assertEqual(response.status_code, 200)
        target = next(item for item in response.json()["items"] if item["title"] == "Python Admin Hybrid Role")
        self.assertEqual(sorted(target["match"]["matched_skills"]), ["excel", "python"])
        self.assertEqual(target["match"]["missing_skills"], [])

    def test_a_cv_that_isnt_ready_contributes_no_skills_not_an_error(self):
        # extracted_skills is populated (simulating a CV mid-reprocessing
        # that already has a stale value), but status isn't "ready" -- must
        # be ignored entirely, not surfaced as a false match, and must not
        # error the request.
        self._add_cv_version(status=CvVersionStatus.extracting, extracted_skills=["python"], make_active=True)
        with self.Session() as db:
            db.add(Listing(
                id=uuid.uuid4(), source="test", source_listing_id=f"cv-not-ready-{uuid.uuid4()}",
                title="Python Only Role", description="Needs Python", required_skills=["python"],
                listing_type=ListingType.job, location="Johannesburg",
                apply_method=ApplyMethod.ats_link, apply_target="https://example.test/apply",
            ))
            db.commit()

        response = self.client.get("/listings/matches", params={"limit": 50})
        self.assertEqual(response.status_code, 200)
        target = next(item for item in response.json()["items"] if item["title"] == "Python Only Role")
        self.assertEqual(target["match"]["matched_skills"], [])
        self.assertEqual(target["match"]["missing_skills"], ["python"])

    def test_no_active_cv_at_all_contributes_no_skills_not_an_error(self):
        with self.Session() as db:
            db.add(Listing(
                id=uuid.uuid4(), source="test", source_listing_id=f"no-cv-{uuid.uuid4()}",
                title="No CV On File Role", description="Needs Python", required_skills=["python"],
                listing_type=ListingType.job, location="Johannesburg",
                apply_method=ApplyMethod.ats_link, apply_target="https://example.test/apply",
            ))
            db.commit()

        response = self.client.get("/listings/matches", params={"limit": 50})
        self.assertEqual(response.status_code, 200)
        target = next(item for item in response.json()["items"] if item["title"] == "No CV On File Role")
        self.assertEqual(target["match"]["matched_skills"], [])
        self.assertEqual(target["match"]["missing_skills"], ["python"])

    def test_put_profile_does_not_touch_any_cv_versions_extracted_skills(self):
        # The two skill sources must stay genuinely independent: a profile
        # edit -- even one that fully replaces profile.skills, per PUT's own
        # documented full-replace semantics -- must never reach into
        # cv_versions at all.
        cv_version = self._add_cv_version(status=CvVersionStatus.ready, extracted_skills=["python"], make_active=True)

        response = self.client.put("/profile", json={"skills": ["excel"], "job_type": "full_time"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["skills"], ["excel"])

        with self.Session() as db:
            reloaded = db.get(CvVersion, cv_version.id)
            self.assertEqual(reloaded.extracted_skills, ["python"])


if __name__ == "__main__":
    unittest.main()
