import unittest

from app.celery_app import celery_app


class CeleryConfigurationTests(unittest.TestCase):
    def test_worker_imports_every_task_module_and_uses_late_acknowledgement(self):
        self.assertEqual(
            set(celery_app.conf.imports),
            {"app.listings.ingestion.tasks", "app.cv_tailoring.tasks", "app.applications.tasks"},
        )
        self.assertTrue(celery_app.conf.task_acks_late)
        self.assertTrue(celery_app.conf.task_reject_on_worker_lost)
        self.assertTrue(celery_app.conf.task_track_started)

    def test_default_loader_registers_tailoring_and_email_tasks(self):
        celery_app.loader.import_default_modules()
        for task_name in (
            "app.cv_tailoring.tasks.extract_cv_version",
            "app.cv_tailoring.tasks.process_tailored_document",
            "app.cv_tailoring.tasks.reconcile_stale_tailoring",
            "app.cv_tailoring.tasks.reconcile_stale_cv_extractions",
            "app.listings.ingestion.tasks.deactivate_stale_listings",
            "app.applications.tasks.send_application_email",
        ):
            self.assertIn(task_name, celery_app.tasks)

    def test_beat_schedule_covers_ingestion_and_both_reconciliation_jobs(self):
        scheduled_tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
        self.assertEqual(
            scheduled_tasks,
            {
                "app.listings.ingestion.tasks.ingest_adzuna",
                "app.listings.ingestion.tasks.ingest_himalayas",
                "app.listings.ingestion.tasks.ingest_vacancyupdate",
                "app.listings.ingestion.tasks.deactivate_stale_listings",
                "app.listings.ingestion.tasks.deactivate_expired_listings",
                "app.cv_tailoring.tasks.reconcile_stale_tailoring",
                "app.cv_tailoring.tasks.reconcile_stale_cv_extractions",
            },
        )
