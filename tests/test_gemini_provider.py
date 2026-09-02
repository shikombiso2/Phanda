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
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

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

    def test_timeout_and_rate_limit_are_retryable(self):
        with self.assertRaises(ProviderError) as timeout:
            self._generate(error=httpx.TimeoutException("timeout"))
        self.assertTrue(timeout.exception.retryable)
        with self.assertRaises(ProviderError) as rate_limit:
            self._generate(FakeResponse(status_code=429))
        self.assertTrue(rate_limit.exception.retryable)

    def test_provider_refusal_is_not_retryable(self):
        with self.assertRaises(ProviderError) as refusal:
            self._generate(FakeResponse(status_code=400))
        self.assertEqual(refusal.exception.code, "provider_rejected_request")
        self.assertFalse(refusal.exception.retryable)
