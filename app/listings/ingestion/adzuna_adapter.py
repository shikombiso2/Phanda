import httpx

from app.core.config import get_settings
from app.listings.ingestion.normalize import NormalizedListing, normalize_adzuna


class AdzunaClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def fetch_page(self, page: int = 1, results_per_page: int = 50) -> list[NormalizedListing]:
        if not self.settings.adzuna_app_id or not self.settings.adzuna_app_key:
            return []

        url = f"https://api.adzuna.com/v1/api/jobs/{self.settings.adzuna_country}/search/{page}"
        params = {
            "app_id": self.settings.adzuna_app_id,
            "app_key": self.settings.adzuna_app_key,
            "results_per_page": results_per_page,
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
        return [normalize_adzuna(row) for row in response.json().get("results", [])]

