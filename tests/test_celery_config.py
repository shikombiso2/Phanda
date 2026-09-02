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
            "app.applications.tasks.send_application_email",
        ):
            self.assertIn(task_name, celery_app.tasks)
