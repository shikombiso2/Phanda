import unittest
import uuid

import jwt

from app.core.config import get_settings
from app.core.security import (
    WeakPasswordError,
    create_access_token,
    generate_refresh_token_secret,
    hash_password,
    hash_refresh_token,
    normalize_email,
    validate_password_strength,
    verify_password,
)


class PasswordHashingTests(unittest.TestCase):
    def test_hash_is_not_the_plaintext_password(self):
        hashed = hash_password("a-real-password-123")
        self.assertNotEqual(hashed, "a-real-password-123")
        self.assertTrue(hashed.startswith("$argon2id$"))

    def test_correct_password_verifies(self):
        hashed = hash_password("a-real-password-123")
        self.assertTrue(verify_password("a-real-password-123", hashed))

    def test_wrong_password_does_not_verify(self):
        hashed = hash_password("a-real-password-123")
        self.assertFalse(verify_password("something-else", hashed))

    def test_corrupt_hash_fails_closed_rather_than_raising(self):
        self.assertFalse(verify_password("anything", "not-a-real-hash"))

    def test_two_hashes_of_the_same_password_differ(self):
        # Argon2 salts automatically; equal outputs would mean no salt was applied.
        self.assertNotEqual(hash_password("same-password-1"), hash_password("same-password-1"))


class PasswordStrengthTests(unittest.TestCase):
    def test_short_password_is_rejected(self):
        with self.assertRaises(WeakPasswordError):
            validate_password_strength("short1")

    def test_common_password_is_rejected(self):
        with self.assertRaises(WeakPasswordError):
            validate_password_strength("password123")

    def test_password_matching_email_local_part_is_rejected(self):
        with self.assertRaises(WeakPasswordError):
            validate_password_strength("jsmith", email="jsmith@example.com")

    def test_reasonable_password_is_accepted(self):
        validate_password_strength("Correct-Horse-Battery-1", email="user@example.com")  # must not raise


class RefreshTokenSecretTests(unittest.TestCase):
    def test_secrets_are_unique_and_high_entropy(self):
        first = generate_refresh_token_secret()
        second = generate_refresh_token_secret()
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)

    def test_hash_is_deterministic_and_not_the_secret(self):
        secret = generate_refresh_token_secret()
        self.assertEqual(hash_refresh_token(secret), hash_refresh_token(secret))
        self.assertNotEqual(hash_refresh_token(secret), secret)


class EmailNormalizationTests(unittest.TestCase):
    def test_normalizes_case_and_whitespace(self):
        self.assertEqual(normalize_email(" User@Example.com "), "user@example.com")


class AccessTokenTests(unittest.TestCase):
    def test_access_token_carries_type_and_subject(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[get_settings().jwt_algorithm])
        self.assertEqual(payload["sub"], str(user_id))
        self.assertEqual(payload["type"], "access")


if __name__ == "__main__":
    unittest.main()
