from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("phanda", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = {
    "ingest-adzuna-every-4-hours": {
        "task": "app.listings.ingestion.tasks.ingest_adzuna",
        "schedule": 4 * 60 * 60,
    }
}

