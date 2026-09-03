"""CV extraction reconciliation against real PostgreSQL.

Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set.
"""
from __future__ import annotations

import os
import unittest
import uuid
from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.models import CvVersion, CvVersionStatus, User, utcnow
from app.cv_tailoring.tasks import find_stale_cv_versions
from tests.postgres_harness import PostgresHarness


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class StaleCvExtractionTests(unittest.TestCase):
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

    def _cv(self, db, user_id, *, version_number: int, status: CvVersionStatus, lease_expires_at) -> CvVersion:
        version = CvVersion(
            id=uuid.uuid4(), user_id=user_id, version_number=version_number, status=status,
            storage_key=f"test/{uuid.uuid4()}.txt", filename="cv.txt", content_type="text/plain",
            byte_size=10, sha256=uuid.uuid4().hex * 2, processing_lease_expires_at=lease_expires_at,
        )
        db.add(version)
        return version

    def test_expired_lease_in_uploaded_or_extracting_is_found_as_stale(self):
        with self.Session() as db:
            user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            db.add(user)
            db.flush()
            # uq_cv_version_number is (user_id, version_number): each of this
            # user's versions needs a distinct number, same as production.
            expired_uploaded = self._cv(db, user.id, version_number=1, status=CvVersionStatus.uploaded, lease_expires_at=utcnow() - timedelta(minutes=1))
            expired_extracting = self._cv(db, user.id, version_number=2, status=CvVersionStatus.extracting, lease_expires_at=utcnow() - timedelta(minutes=1))
            still_valid = self._cv(db, user.id, version_number=3, status=CvVersionStatus.extracting, lease_expires_at=utcnow() + timedelta(minutes=10))
            no_lease_yet = self._cv(db, user.id, version_number=4, status=CvVersionStatus.uploaded, lease_expires_at=None)
            db.commit()

            stale = set(find_stale_cv_versions(db))

            self.assertIn(expired_uploaded.id, stale)
            self.assertIn(expired_extracting.id, stale)
            self.assertNotIn(still_valid.id, stale)
            self.assertNotIn(no_lease_yet.id, stale)

    def test_ready_and_failed_versions_are_never_considered_stale(self):
        with self.Session() as db:
            user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            db.add(user)
            db.flush()
            ready = self._cv(db, user.id, version_number=1, status=CvVersionStatus.ready, lease_expires_at=utcnow() - timedelta(days=1))
            failed = self._cv(db, user.id, version_number=2, status=CvVersionStatus.failed, lease_expires_at=utcnow() - timedelta(days=1))
            db.commit()

            stale = set(find_stale_cv_versions(db))

            self.assertNotIn(ready.id, stale)
            self.assertNotIn(failed.id, stale)


if __name__ == "__main__":
    unittest.main()
