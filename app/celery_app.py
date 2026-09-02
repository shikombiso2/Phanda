from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()


@setup_logging.connect
def _configure_worker_logging(**_kwargs) -> None:
    """Celery installs its own logging by default; this opts out of that so
    worker and beat processes emit the same structured JSON as the API."""
    configure_logging()


celery_app = Celery("phanda", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    imports=(
        "app.listings.ingestion.tasks",
        "app.cv_tailoring.tasks",
        "app.applications.tasks",
    ),
    # Generation work is idempotent and lease-protected. Acknowledging after
    # execution lets Redis redeliver work after a worker crash.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
)
celery_app.conf.beat_schedule = {
    "ingest-adzuna-every-4-hours": {
        "task": "app.listings.ingestion.tasks.ingest_adzuna",
        "schedule": 4 * 60 * 60,
    },
    "deactivate-stale-listings-daily": {
        "task": "app.listings.ingestion.tasks.deactivate_stale_listings",
        "schedule": 24 * 60 * 60,
    },
    "reconcile-stale-tailoring-every-5-minutes": {
        "task": "app.cv_tailoring.tasks.reconcile_stale_tailoring",
        "schedule": 5 * 60,
    },
    "reconcile-stale-cv-extractions-every-5-minutes": {
        "task": "app.cv_tailoring.tasks.reconcile_stale_cv_extractions",
        "schedule": 5 * 60,
    },
}
