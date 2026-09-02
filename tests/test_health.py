import unittest
from unittest.mock import patch

from app.core.health import _check_database, _check_redis, _check_storage, ready


class HealthChecksTests(unittest.TestCase):
    @patch("app.core.health.engine")
    def test_database_check_returns_false_on_connection_error(self, engine):
        engine.connect.side_effect = RuntimeError("db down")
        self.assertFalse(_check_database())

    @patch("app.core.health.redis")
    def test_redis_check_returns_false_on_connection_error(self, redis_module):
        redis_module.from_url.side_effect = RuntimeError("redis down")
        self.assertFalse(_check_redis())

    def test_storage_check_true_for_local_storage(self):
        self.assertTrue(_check_storage())

    @patch("app.core.health._check_storage", return_value=True)
    @patch("app.core.health._check_redis", return_value=True)
    @patch("app.core.health._check_database", return_value=True)
    def test_ready_reports_200_when_all_dependencies_are_up(self, *_mocks):
        response = type("R", (), {"status_code": None})()
        result = ready(response)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(response.status_code, 200)

    @patch("app.core.health._check_storage", return_value=True)
    @patch("app.core.health._check_redis", return_value=False)
    @patch("app.core.health._check_database", return_value=True)
    def test_ready_reports_503_when_a_dependency_is_down(self, *_mocks):
        response = type("R", (), {"status_code": None})()
        result = ready(response)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(result["checks"]["redis"])


if __name__ == "__main__":
    unittest.main()
