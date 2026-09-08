from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.applications.router import router as applications_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.listings.router import router as listings_router
from app.listings.ingestion.router import router as ingestion_router
from app.monetization.revenuecat_webhook import router as revenuecat_router
from app.profiles.router import router as profiles_router
from app.cv_tailoring.router import router as tailoring_router
from app.saved.router import router as saved_router
from app.skill_gap.router import router as skill_gap_router


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    settings.assert_safe_for_environment()
    app = FastAPI(title="Phanda Backend", version="0.1.0")
    install_error_handlers(app)

    # phanda-web (and anything else browser-based) needs this to call the
    # API cross-origin at all -- without it the browser blocks the response
    # before JS ever sees it, regardless of what the API itself returns.
    # allow_origins is deliberately never "*": that combination with
    # allow_credentials=True is invalid per the CORS spec (a wildcard origin
    # cannot be paired with credentialed requests) and browsers reject it
    # outright. The allowed list comes from config rather than being
    # hardcoded, since a developer's LAN IP for testing on a phone changes
    # per network -- see Settings.cors_allowed_origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(profiles_router)
    app.include_router(tailoring_router)
    app.include_router(listings_router)
    app.include_router(ingestion_router)
    app.include_router(applications_router)
    app.include_router(saved_router)
    app.include_router(skill_gap_router)
    app.include_router(revenuecat_router)

    return app
