from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://phanda:phanda@localhost:5432/phanda"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24 * 30

    otp_ttl_minutes: int = 10
    otp_dev_mode: bool = True
    otp_dev_code: str = "123456"
    sms_provider: str = "none"
    sms_api_url: str | None = None
    sms_api_key: str | None = None
    sms_from: str = "Phanda"

    monthly_free_cv_tailor: int = 3
    monthly_free_skill_gap_roadmap: int = 3

    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    adzuna_country: str = "za"

    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "af-south-1"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    email_provider: str = "sendgrid"
    sendgrid_api_key: str | None = None
    mailgun_api_key: str | None = None
    mailgun_domain: str | None = None
    email_from: str = "applications@phanda.example"

    revenuecat_webhook_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
