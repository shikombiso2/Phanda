from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_JWT_SECRET = "change-me"


class Settings(BaseSettings):
    # No default: the production-only guards below (RevenueCat/Adzuna
    # secrets) key off is_production(), which reads this value -- a silent
    # default of "development" would let ENVIRONMENT simply be left unset in
    # production and those guards would never fire. Pydantic raises its own
    # validation error naming the missing field if it's absent.
    environment: str

    database_url: str = "postgresql+psycopg://phanda:phanda@localhost:5433/phanda"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 60

    refresh_reuse_grace_seconds: int = 30
    """How long after a refresh token is rotated away a second presentation of
    that same token is still treated as a benign concurrent refresh rather than
    theft. Mobile clients fire parallel requests; two of them hitting a 401 at
    once both refresh with the token they hold, and without this window the
    second one trips reuse detection and logs the user out of every session.
    Measured from the original rotation and never extended -- see
    app/auth/service.py:_is_benign_concurrent_refresh."""

    google_oauth_client_ids: str | None = None
    """Comma-separated list of accepted Google OAuth client IDs (audiences),
    e.g. the Android client ID and, if a web client ever exists, its ID too."""

    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    """Comma-separated origins the API accepts cross-origin requests from --
    the phanda-web dev server. Defaults to the two localhost variants so a
    fresh checkout works with no configuration; a developer testing from a
    physical phone over Wi-Fi adds their machine's LAN IP here rather than
    it being hardcoded, since that address changes per network."""

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

    himalayas_ingestion_max_pages: int = 10
    """Himalayas caps its page size at 20, so this bounds a run at 200
    listings. No credentials exist for this source -- the API is public and
    unauthenticated -- so there is deliberately no secret to configure."""

    listing_stale_after_days: int = 7

    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "af-south-1"
    local_storage_path: str = ".phanda-storage"

    ai_provider: str = "gemini"
    ai_model: str = "gemini-3.6-flash"
    gemini_api_key: str | None = None
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com"
    ai_timeout_seconds: int = 120
    gemini_thinking_level: str = "low"
    """Passed as generationConfig.thinkingConfig.thinkingLevel on every
    generateContent call. "low" was chosen after live measurement showed the
    model's default spent roughly 3x more tokens on invisible extended
    thinking than on the actual JSON output. "minimal" is a bigger swing
    (skips most reasoning) and needs its own quality validation before use --
    not adopted here."""

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

    def cors_allowed_origins_list(self) -> list[str]:
        return [value.strip() for value in self.cors_allowed_origins.split(",") if value.strip()]

    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def assert_safe_for_environment(self) -> None:
        """Refuse to boot with insecure or incomplete configuration.

        The JWT secret check applies in every environment, not only
        production: it is used on every authenticated request, a wrong value
        does not error visibly, and the previous default let anyone forge a
        token for any user in whatever environment happened to still have it
        set. The remaining checks apply only in production, where a missing
        integration secret means webhooks or ingestion silently no-op rather
        than serving traffic insecurely -- safe to defer to a per-request
        failure everywhere except the one environment where nobody is
        watching for it.
        """
        problems = []
        if self.jwt_secret == INSECURE_DEFAULT_JWT_SECRET:
            problems.append("JWT_SECRET is still the insecure default")
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET is shorter than 32 characters")
        if self.is_production():
            if not self.revenuecat_webhook_secret:
                problems.append("REVENUECAT_WEBHOOK_SECRET is not set")
            if not self.adzuna_app_id:
                problems.append("ADZUNA_APP_ID is not set")
            if not self.adzuna_app_key:
                problems.append("ADZUNA_APP_KEY is not set")
        if problems:
            raise RuntimeError("Refusing to start with insecure or incomplete configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
