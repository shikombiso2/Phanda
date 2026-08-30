from fastapi import FastAPI

from app.applications.router import router as applications_router
from app.auth.router import router as auth_router
from app.core.db import Base, engine
from app.listings.router import router as listings_router
from app.listings.ingestion.router import router as ingestion_router
from app.monetization.revenuecat_webhook import router as revenuecat_router
from app.profiles.router import router as profiles_router
from app.saved.router import router as saved_router
from app.skill_gap.router import router as skill_gap_router


def create_app() -> FastAPI:
    app = FastAPI(title="Phanda Backend", version="0.1.0")

    @app.on_event("startup")
    def create_tables() -> None:
        Base.metadata.create_all(bind=engine)

    app.include_router(auth_router)
    app.include_router(profiles_router)
    app.include_router(listings_router)
    app.include_router(ingestion_router)
    app.include_router(applications_router)
    app.include_router(saved_router)
    app.include_router(skill_gap_router)
    app.include_router(revenuecat_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
