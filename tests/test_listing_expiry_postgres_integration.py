"""Listing expiry against real PostgreSQL.

Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set.
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.models import ApplyMethod, Listing, ListingType, utcnow
from app.listings.ingestion.repository import deactivate_stale_listings
from tests.postgres_harness import PostgresHarness


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class DeactivateStaleListingsTests(unittest.TestCase):
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

    def _listing(self, db, *, last_seen_at, source="adzuna") -> Listing:
        listing = Listing(
            id=uuid.uuid4(), source=source, source_listing_id=str(uuid.uuid4()), title="Role", description="d",
            listing_type=ListingType.job, apply_method=ApplyMethod.ats_link, apply_target="https://example.test",
            last_seen_at=last_seen_at, is_active=True,
        )
        db.add(listing)
        return listing

    def test_listing_not_seen_past_the_grace_period_is_deactivated(self):
        stale_after = get_settings().listing_stale_after_days
        with self.Session() as db:
            stale = self._listing(db, last_seen_at=utcnow() - timedelta(days=stale_after + 1))
            fresh = self._listing(db, last_seen_at=utcnow())
            db.commit()

            deactivated_count = deactivate_stale_listings(db)

            self.assertGreaterEqual(deactivated_count, 1)
            db.refresh(stale)
            db.refresh(fresh)
            self.assertFalse(stale.is_active)
            self.assertTrue(fresh.is_active)

    def test_source_scoping_only_touches_the_named_source(self):
        stale_after = get_settings().listing_stale_after_days
        with self.Session() as db:
            adzuna_stale = self._listing(db, last_seen_at=utcnow() - timedelta(days=stale_after + 1), source="adzuna")
            other_stale = self._listing(db, last_seen_at=utcnow() - timedelta(days=stale_after + 1), source="dev")
            db.commit()

            deactivate_stale_listings(db, source="adzuna")

            db.refresh(adzuna_stale)
            db.refresh(other_stale)
            self.assertFalse(adzuna_stale.is_active)
            self.assertTrue(other_stale.is_active)


if __name__ == "__main__":
    unittest.main()
