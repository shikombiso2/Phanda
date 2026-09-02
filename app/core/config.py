from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_JWT_SECRET = "change-me"


class Settings(BaseSettings):
    environment: str = "development"

    database_url: str = "postgresql+psycopg://phanda:phanda@localhost:5433/phanda"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 60

    google_oauth_client_ids: str | None = None
    """Comma-separated list of accepted Google OAuth client IDs (audiences),
    e.g. the Android client ID and, if a web client ever exists, its ID too."""

    monthly_free_cv_tailor: int = 3
    monthly_free_skill_gap_roadmap: int = 3
    premium_monthly_cv_tailor: int = 100
    tailoring_reservation_minutes: int = 30
    tailoring_max_attempts: int = 3
    cv_extraction_lease_minutes: int = 15
    cv_extraction_max_attempts: int = 3

    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    adzuna_country: str = "za"
    adzuna_ingestion_max_pages: int = 20
    adzuna_ingestion_results_per_page: int = 50
    listing_stale_after_days: int = 7

    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "af-south-1"
    local_storage_path: str = ".phanda-storage"

    ai_provider: str = "gemini"
    ai_model: str = "gemini-2.5-flash"
    gemini_api_key: str | None = None
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com"
    ai_timeout_seconds: int = 60

    email_provider: str = "sendgrid"
    sendgrid_api_key: str | None = None
    mailgun_api_key: str | None = None
    mailgun_domain: str | None = None
    email_from: str = "applications@phanda.example"

    revenuecat_webhook_secret: str | None = None

    ingestion_trigger_secret: str | None = None
    """Shared secret required to manually trigger ingestion outside the Celery
    beat schedule. Unset means the manual-trigger route refuses every request."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def google_client_id_list(self) -> list[str]:
        if not self.google_oauth_client_ids:
            return []
        return [value.strip() for value in self.google_oauth_client_ids.split(",") if value.strip()]

    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def assert_safe_for_environment(self) -> None:
        """Refuse to boot with insecure defaults once ``ENVIRONMENT=production``.

        Every other misconfigured integration (Gemini, RevenueCat, Adzuna,
        email) already fails safely per-request rather than serving traffic
        insecurely, so it is deliberately not checked here. The JWT secret is
        different: it is used on every authenticated request, a wrong value
        does not error visibly, and the previous default let anyone forge a
        token for any user.
        """
        if not self.is_production():
            return
        problems = []
        if self.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
            problems.append("JWT_SECRET is still the insecure default")
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET is shorter than 32 characters")
        if problems:
            raise RuntimeError(
                "Refusing to start in production with insecure configuration: " + "; ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
