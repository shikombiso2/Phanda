"""Himalayas ingestion against real PostgreSQL.

Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set -- same
convention as the other *_postgres_integration.py files, and for the same
reason here specifically: the dedup behaviour under test is enforced by a
real unique constraint (uq_listing_source_id), which a mocked session cannot
stand in for.
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.models import Listing, utcnow
from app.listings.ingestion.normalize import normalize_himalayas
from app.listings.ingestion.repository import deactivate_expired_listings, upsert_listings
from tests.postgres_harness import PostgresHarness


def _raw_job(guid: str, *, title: str = "Senior Python Engineer", expiry_offset_days: int = 30) -> dict:
    expiry = utcnow() + timedelta(days=expiry_offset_days)
    return {
        "guid": guid,
        "applicationLink": guid,
        "title": title,
        "companyName": "Remote Co",
        "companySlug": "remote-co",
        "description": "<p>Build services in <strong>Python</strong>.</p><ul><li>Postgres</li></ul>",
        "employmentType": "Full Time",
        "locationRestrictions": ["United States"],
        "categories": ["Software-Engineering"],
        "parentCategories": ["Developer"],
        "minSalary": 100000,
        "maxSalary": 150000,
        "salaryPeriod": "annual",
        "currency": "USD",
        "pubDate": int((utcnow() - timedelta(days=1)).timestamp()),
        "expiryDate": int(expiry.timestamp()),
    }


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class HimalayasIngestionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = PostgresHarness()
        cls.harness.create()
        cls.engine = create_engine(cls.harness.test_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.harness.drop()

    def test_ingesting_the_same_guid_twice_updates_in_place(self):
        guid = f"https://himalayas.app/companies/remote-co/jobs/{uuid.uuid4().hex[:12]}"

        with self.Session() as db:
            upsert_listings(db, [normalize_himalayas(_raw_job(guid, title="Senior Python Engineer"))])
            upsert_listings(db, [normalize_himalayas(_raw_job(guid, title="Staff Python Engineer"))])

            rows = db.scalars(
                select(Listing).where(Listing.source == "himalayas", Listing.source_listing_id == guid)
            ).all()

            self.assertEqual(len(rows), 1, "re-ingesting the same guid must update in place, not insert a duplicate")
            self.assertEqual(rows[0].title, "Staff Python Engineer", "the second pull's values must win")
            # Units are stored as the source reported them, not converted.
            self.assertEqual(rows[0].salary_period, "annual")
            self.assertEqual(rows[0].salary_currency, "USD")

    def test_a_listing_past_its_expiry_date_is_not_active(self):
        live_guid = f"https://himalayas.app/companies/remote-co/jobs/{uuid.uuid4().hex[:12]}"
        expired_guid = f"https://himalayas.app/companies/remote-co/jobs/{uuid.uuid4().hex[:12]}"

        with self.Session() as db:
            upsert_listings(
                db,
                [
                    normalize_himalayas(_raw_job(live_guid, expiry_offset_days=30)),
                    normalize_himalayas(_raw_job(expired_guid, expiry_offset_days=-1)),
                ],
            )

            expired = db.scalar(select(Listing).where(Listing.source_listing_id == expired_guid))
            live = db.scalar(select(Listing).where(Listing.source_listing_id == live_guid))
            self.assertFalse(expired.is_active, "a listing ingested already past its expiryDate must not be active")
            self.assertTrue(live.is_active)

            # And one that lapses after ingestion is caught by the sweep.
            live.expires_at = utcnow() - timedelta(minutes=1)
            db.commit()
            deactivate_expired_listings(db)
            db.refresh(live)
            self.assertFalse(live.is_active)


if __name__ == "__main__":
    unittest.main()
