import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app.core.config import get_settings
from app.listings.ingestion.adzuna_adapter import AdzunaClient


def _response(results: list[dict], status_code: int = 200) -> Mock:
    response = Mock(status_code=status_code)
    response.json.return_value = {"results": results}
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=Mock(), response=response)
    else:
        response.raise_for_status.side_effect = None
    return response


def _job(job_id: str) -> dict:
    return {"id": job_id, "title": "Admin Assistant", "description": "Excel required", "redirect_url": "https://example.test/apply"}


class AdzunaClientTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.original_id, self.original_key = self.settings.adzuna_app_id, self.settings.adzuna_app_key
        self.settings.adzuna_app_id, self.settings.adzuna_app_key = "id", "key"

    def tearDown(self):
        self.settings.adzuna_app_id, self.settings.adzuna_app_key = self.original_id, self.original_key

    def test_missing_credentials_returns_empty_without_a_request(self):
        self.settings.adzuna_app_id = None
        result = asyncio.run(AdzunaClient().fetch_all())
        self.assertEqual(result, [])

    @patch("app.listings.ingestion.adzuna_adapter.httpx.AsyncClient")
    def test_fetch_all_stops_on_a_short_page(self, client_class):
        client = AsyncMock()
        client.get.return_value = _response([_job("1"), _job("2")])  # 2 < results_per_page -> last page
        client_class.return_value.__aenter__.return_value = client

        rows = asyncio.run(AdzunaClient().fetch_all(max_pages=10, results_per_page=50))

        self.assertEqual(len(rows), 2)
        self.assertEqual(client.get.call_count, 1)

    @patch("app.listings.ingestion.adzuna_adapter.httpx.AsyncClient")
    @patch("app.listings.ingestion.adzuna_adapter.asyncio.sleep", new_callable=AsyncMock)
    def test_fetch_all_paginates_until_max_pages(self, _sleep, client_class):
        client = AsyncMock()
        full_page = [_job(str(i)) for i in range(2)]
        client.get.return_value = _response(full_page)  # always full -> would paginate forever without a cap
        client_class.return_value.__aenter__.return_value = client

        rows = asyncio.run(AdzunaClient().fetch_all(max_pages=3, results_per_page=2))

        self.assertEqual(client.get.call_count, 3)
        self.assertEqual(len(rows), 6)

    @patch("app.listings.ingestion.adzuna_adapter.httpx.AsyncClient")
    @patch("app.listings.ingestion.adzuna_adapter.asyncio.sleep", new_callable=AsyncMock)
    def test_a_failed_page_stops_pagination_but_keeps_earlier_results(self, _sleep, client_class):
        client = AsyncMock()
        client.get.side_effect = [_response([_job("1"), _job("2")]), _response([], status_code=500), _response([], status_code=500), _response([], status_code=500)]
        client_class.return_value.__aenter__.return_value = client

        rows = asyncio.run(AdzunaClient().fetch_all(max_pages=5, results_per_page=2))

        self.assertEqual(len(rows), 2, "the first page's results must survive a later page's failure")

    @patch("app.listings.ingestion.adzuna_adapter.httpx.AsyncClient")
    @patch("app.listings.ingestion.adzuna_adapter.asyncio.sleep", new_callable=AsyncMock)
    def test_a_retryable_status_is_retried_then_succeeds(self, _sleep, client_class):
        client = AsyncMock()
        client.get.side_effect = [_response([], status_code=503), _response([_job("1")])]
        client_class.return_value.__aenter__.return_value = client

        rows = asyncio.run(AdzunaClient().fetch_page(page=1, results_per_page=50))

        self.assertEqual(len(rows), 1)
        self.assertEqual(client.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
