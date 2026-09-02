import unittest

from app.core.config import get_settings
from scripts.backfill_legacy_cv_versions import _verified_s3_key


class LegacyCvBackfillTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.previous_bucket = self.settings.s3_bucket
        self.settings.s3_bucket = "phanda-private"

    def tearDown(self):
        self.settings.s3_bucket = self.previous_bucket

    def test_accepts_only_configured_s3_bucket_key(self):
        self.assertEqual(_verified_s3_key("s3://phanda-private/users/a/cv.pdf"), "users/a/cv.pdf")
        self.assertIsNone(_verified_s3_key("s3://other-bucket/users/a/cv.pdf"))

    def test_rejects_local_and_public_legacy_references(self):
        self.assertIsNone(_verified_s3_key("local://legacy/cv.pdf"))
        self.assertIsNone(_verified_s3_key("https://example.test/cv.pdf"))
