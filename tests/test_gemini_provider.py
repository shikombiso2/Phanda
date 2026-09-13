import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from app.core.config import get_settings
from app.cv_tailoring.gemini import GeminiProvider
from app.cv_tailoring.provider import ProviderError
from app.cv_tailoring.schemas import TailoredCv


VALID_CV = {
    "sections": [
        {"name": "Professional Summary", "claims": [{"text": "Python", "source_fact_ids": ["fact_1"], "job_requirement_ids": []}]},
        {"name": "Skills", "claims": [{"text": "Python", "source_fact_ids": ["fact_1"], "job_requirement_ids": []}]},
    ],
    "cover_letter": [{"text": "Python", "source_fact_ids": ["fact_1"], "job_requirement_ids": []}],
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, response=None, error=None, **_):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.response


class GeminiProviderContractTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.original_key = self.settings.gemini_api_key
        self.settings.gemini_api_key = "test-key"

    def tearDown(self):
        self.settings.gemini_api_key = self.original_key

    def _generate(self, response=None, error=None):
        with patch("app.cv_tailoring.gemini.httpx.AsyncClient", lambda **kwargs: FakeClient(response=response, error=error, **kwargs)):
            return asyncio.run(GeminiProvider()._generate(TailoredCv, {"task": "test"}))

    def test_valid_schema_response_maps_to_internal_model(self):
        response = FakeResponse(payload={"candidates": [{"content": {"parts": [{"text": json.dumps(VALID_CV)}]}}]})
        self.assertEqual(self._generate(response).sections[0].name, "Professional Summary")

    def test_malformed_and_missing_fields_are_rejected(self):
        response = FakeResponse(payload={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
        with self.assertRaisesRegex(ProviderError, "malformed_provider_output"):
            self._generate(response)

    def test_timeout_and_server_errors_are_retryable(self):
        with self.assertRaises(ProviderError) as timeout:
            self._generate(error=httpx.TimeoutException("timeout"))
        self.assertTrue(timeout.exception.retryable)
        self.assertIsNone(timeout.exception.retry_after_seconds)
        with self.assertRaises(ProviderError) as unavailable:
            self._generate(FakeResponse(status_code=503))
        self.assertEqual(unavailable.exception.code, "provider_unavailable")
        self.assertTrue(unavailable.exception.retryable)
        self.assertIsNone(unavailable.exception.retry_after_seconds)

    def test_rate_limit_is_retryable_with_a_backoff_not_an_immediate_retry(self):
        # No Retry-After header: falls back to the 30s minimum, not the
        # generic 503 path's immediate retry.
        with self.assertRaises(ProviderError) as no_header:
            self._generate(FakeResponse(status_code=429))
        self.assertEqual(no_header.exception.code, "provider_rate_limited")
        self.assertTrue(no_header.exception.retryable)
        self.assertEqual(no_header.exception.retry_after_seconds, 30.0)

        # A Retry-After longer than 30s is honoured rather than clamped down.
        with self.assertRaises(ProviderError) as with_header:
            self._generate(FakeResponse(status_code=429, headers={"Retry-After": "45"}))
        self.assertEqual(with_header.exception.retry_after_seconds, 45.0)

        # A Retry-After shorter than 30s is still floored at 30s.
        with self.assertRaises(ProviderError) as short_header:
            self._generate(FakeResponse(status_code=429, headers={"Retry-After": "5"}))
        self.assertEqual(short_header.exception.retry_after_seconds, 30.0)

    def test_provider_refusal_is_not_retryable(self):
        with self.assertRaises(ProviderError) as refusal:
            self._generate(FakeResponse(status_code=400))
        self.assertEqual(refusal.exception.code, "provider_rejected_request")
        self.assertFalse(refusal.exception.retryable)
