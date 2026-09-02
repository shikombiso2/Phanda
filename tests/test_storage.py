import tempfile
import unittest
from unittest.mock import Mock, patch

from app.core.config import get_settings
from app.core.storage import create_download_url, get_bytes, put_bytes


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.previous_bucket = self.settings.s3_bucket
        self.previous_path = self.settings.local_storage_path

    def tearDown(self):
        self.settings.s3_bucket = self.previous_bucket
        self.settings.local_storage_path = self.previous_path

    def test_local_storage_uses_opaque_key_and_has_no_download_url(self):
        self.settings.s3_bucket = None
        with tempfile.TemporaryDirectory() as directory:
            self.settings.local_storage_path = directory
            self.assertEqual(put_bytes(b"private", "users/u1/cv.pdf", "application/pdf"), "users/u1/cv.pdf")
            self.assertEqual(get_bytes("users/u1/cv.pdf"), b"private")
            self.assertIsNone(create_download_url("users/u1/cv.pdf", "cv.pdf"))

    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            put_bytes(b"x", "users/u1/../../secret.pdf")

    def test_s3_download_is_short_lived_and_never_uses_an_s3_uri(self):
        self.settings.s3_bucket = "phanda-private"
        client = Mock()
        client.generate_presigned_url.return_value = "https://storage.example/signed"
        with patch("app.core.storage._client", return_value=client):
            url = create_download_url("users/u1/cv.pdf", "CV: candidate.pdf", expires_in=300)
        self.assertEqual(url, "https://storage.example/signed")
        kwargs = client.generate_presigned_url.call_args.kwargs
        self.assertEqual(kwargs["Params"]["Bucket"], "phanda-private")
        self.assertEqual(kwargs["Params"]["Key"], "users/u1/cv.pdf")
        self.assertEqual(kwargs["ExpiresIn"], 300)
        self.assertNotIn("s3://", url)
