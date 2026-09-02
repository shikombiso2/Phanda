import unittest

from app.core.config import Settings


class ProductionSafetyTests(unittest.TestCase):
    def test_development_boots_with_defaults(self):
        Settings(environment="development").assert_safe_for_environment()  # must not raise

    def test_production_refuses_default_secret(self):
        with self.assertRaises(RuntimeError):
            Settings(environment="production", jwt_secret="change-me").assert_safe_for_environment()

    def test_production_refuses_short_secret(self):
        with self.assertRaises(RuntimeError):
            Settings(environment="production", jwt_secret="short").assert_safe_for_environment()

    def test_production_accepts_a_real_secret(self):
        settings = Settings(environment="production", jwt_secret="x" * 40)
        settings.assert_safe_for_environment()  # must not raise

    def test_google_client_id_list_parses_comma_separated_values(self):
        settings = Settings(google_oauth_client_ids=" abc.apps.googleusercontent.com , def.apps.googleusercontent.com ")
        self.assertEqual(
            settings.google_client_id_list(),
            ["abc.apps.googleusercontent.com", "def.apps.googleusercontent.com"],
        )

    def test_google_client_id_list_empty_when_unset(self):
        self.assertEqual(Settings(google_oauth_client_ids=None).google_client_id_list(), [])


if __name__ == "__main__":
    unittest.main()
