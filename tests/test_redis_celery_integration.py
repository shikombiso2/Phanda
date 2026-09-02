"""Opt-in verification of a real Celery worker against Redis and disposable PostgreSQL.

Run only with ``PHANDA_RUN_REDIS_CELERY_INTEGRATION=1``.  The test uses Redis
database 15, a uniquely named temporary PostgreSQL database, temporary local
object storage, and a local synthetic Gemini-compatible HTTP server.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import redis
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.applications.tasks import send_application_email_task
from app.celery_app import celery_app
from app.core.models import (
    Application, ApplicationStatus, ApplicationSubmissionStatus, AppliedVia, ApplyMethod, CvVersion,
    CvVersionStatus, ExperienceLevel, FeatureUsage, JobType, Listing, ListingType, Profile,
    ReservationStatus, TailoredDocument, TailoredDocumentStatus, TailoringRequestReservation, User, utcnow,
)
from app.cv_tailoring.tasks import process_tailored_document_task, reconcile_stale_tailoring
from app.monetization.gate import reserve_tailoring_request
from tests.postgres_harness import PostgresHarness


class _ProviderState:
    def __init__(self) -> None:
        self.analysis_started = threading.Event()
        self.allow_blocked_response = threading.Event()
        self.allow_blocked_response.set()
        self.block_candidate_prefixes: set[str] = set()
        self.transient_remaining: dict[str, int] = {}
        self.calls_by_candidate: dict[str, int] = {}
        self.lock = threading.Lock()


class _SyntheticGeminiHandler(BaseHTTPRequestHandler):
    state: _ProviderState

    def do_POST(self) -> None:  # noqa: N802
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        payload = json.loads(request["contents"][0]["parts"][0]["text"])
        task = payload["task"]
        candidate = payload.get("candidate_cv", "")
        if task.startswith("Analyze"):
            with self.state.lock:
                self.state.calls_by_candidate[candidate] = self.state.calls_by_candidate.get(candidate, 0) + 1
                should_block = next((prefix for prefix in self.state.block_candidate_prefixes if candidate.startswith(prefix)), None)
                if should_block:
                    self.state.block_candidate_prefixes.remove(should_block)
                    self.state.analysis_started.set()
            if should_block:
                self.state.allow_blocked_response.wait(timeout=15)
            with self.state.lock:
                remaining = self.state.transient_remaining.get(candidate, 0)
                if remaining:
                    self.state.transient_remaining[candidate] = remaining - 1
                    return self._send(429, {"error": {"message": "synthetic temporary failure"}})
            fact = {
                "id": "fact_1",
                "category": "experience",
                "normalized_value": candidate,
                "source_spans": [{"start": 0, "end": len(candidate), "excerpt": candidate}],
                "confidence": 1,
            }
            return self._response({
                "candidate_facts": {"facts": [fact]},
                "job_requirements": {"requirements": [{"id": "job_1", "category": "skill", "text": "Python", "required": True}]},
                "strategy": {"emphasize_fact_ids": ["fact_1"], "allowed_job_requirement_ids": ["job_1"], "notes": []},
            })
        return self._response({
            "sections": [
                {"name": "Professional Summary", "claims": [{"text": candidate or "Python", "source_fact_ids": ["fact_1"], "job_requirement_ids": ["job_1"]}]},
                {"name": "Skills", "claims": [{"text": "Python", "source_fact_ids": ["fact_1"], "job_requirement_ids": ["job_1"]}]},
            ],
            "cover_letter": [{"text": "Python", "source_fact_ids": ["fact_1"], "job_requirement_ids": ["job_1"]}],
        })

    def _response(self, response: dict) -> None:
        self._send(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(response)}]}}]})

    def _send(self, status: int, response: dict) -> None:
        data = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args) -> None:
        return


@unittest.skipUnless(os.getenv("PHANDA_RUN_REDIS_CELERY_INTEGRATION") == "1", "requires explicit Redis/Celery integration run")
class RedisCeleryIntegrationTests(unittest.TestCase):
    redis_url = "redis://localhost:6379/15"

    @classmethod
    def setUpClass(cls):
        cls.redis = redis.Redis.from_url(cls.redis_url)
        cls.redis.ping()
        cls.redis.flushdb()
        cls.harness = PostgresHarness()
        cls.harness.create()
        cls.engine = create_engine(cls.harness.test_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.storage = tempfile.TemporaryDirectory()
        cls.state = _ProviderState()
        _SyntheticGeminiHandler.state = cls.state
        cls.provider_server = ThreadingHTTPServer(("127.0.0.1", 0), _SyntheticGeminiHandler)
        cls.provider_thread = threading.Thread(target=cls.provider_server.serve_forever, daemon=True)
        cls.provider_thread.start()
        cls.worker_env = os.environ | {
            "DATABASE_URL": cls.harness.test_url.render_as_string(hide_password=False),
            "REDIS_URL": cls.redis_url,
            "LOCAL_STORAGE_PATH": cls.storage.name,
            "GEMINI_API_KEY": "synthetic-test-key",
            "GEMINI_API_BASE_URL": f"http://127.0.0.1:{cls.provider_server.server_port}",
            "EMAIL_PROVIDER": "none",
        }
        cls.original_broker = celery_app.conf.broker_url
        cls.original_backend = celery_app.conf.result_backend
        celery_app.conf.update(broker_url=cls.redis_url, result_backend=cls.redis_url)
        cls.worker = None
        cls._start_worker()

    @classmethod
    def tearDownClass(cls):
        cls._stop_worker()
        celery_app.conf.update(broker_url=cls.original_broker, result_backend=cls.original_backend)
        cls.provider_server.shutdown()
        cls.provider_server.server_close()
        cls.provider_thread.join(timeout=5)
        cls.engine.dispose()
        cls.harness.drop()
        cls.redis.flushdb()
        cls.storage.cleanup()

    @classmethod
    def _start_worker(cls):
        hostname = f"phanda-celery-test-{uuid.uuid4().hex[:8]}@%h"
        cls.worker = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "app.celery_app.celery_app", "worker", "--pool=solo", "--loglevel=WARNING", f"--hostname={hostname}"],
            cwd=Path(__file__).resolve().parents[1], env=cls.worker_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if cls.worker.poll() is not None:
                raise RuntimeError("Celery worker exited during startup")
            if celery_app.control.ping(timeout=1):
                return
            time.sleep(0.2)
        raise RuntimeError("Celery worker did not respond to ping")

    @classmethod
    def _stop_worker(cls):
        if cls.worker and cls.worker.poll() is None:
            cls.worker.terminate()
            try:
                cls.worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.worker.kill()
                cls.worker.wait(timeout=10)

    def setUp(self):
        with self.Session() as db:
            self.user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            self.profile = Profile(user_id=self.user.id, job_type=JobType.any, experience_level=ExperienceLevel.none, skills=[], industries=[])
            db.add_all([self.user, self.profile])
            db.commit()

    def _reserve(self, label: str):
        candidate = f"{label} Python developer with two years of production software delivery experience at Acme Ltd."
        with self.Session() as db:
            listing = Listing(
                id=uuid.uuid4(), source="celery-test", source_listing_id=str(uuid.uuid4()), title="Python Developer",
                description="Python role", required_skills=["Python"], apply_method=ApplyMethod.ats_link,
                apply_target="https://example.test/apply", listing_type=ListingType.job,
            )
            version = CvVersion(
                id=uuid.uuid4(), user_id=self.user.id, version_number=self._next_version(db), status=CvVersionStatus.ready,
                storage_key=f"users/{self.user.id}/{uuid.uuid4()}.txt", filename="cv.txt", content_type="text/plain",
                byte_size=len(candidate), sha256=uuid.uuid4().hex * 2, extracted_text_key=f"users/{self.user.id}/{uuid.uuid4()}.txt", ready_at=utcnow(),
            )
            db.add_all([listing, version])
            db.flush()
            Path(self.storage.name, version.extracted_text_key).parent.mkdir(parents=True, exist_ok=True)
            Path(self.storage.name, version.extracted_text_key).write_text(candidate, encoding="utf-8")
            result = reserve_tailoring_request(db, user_id=self.user.id, listing=listing, profile=db.get(Profile, self.user.id), cv_version=version, idempotency_key=f"{label}-{uuid.uuid4().hex}")
            return result.document.id, candidate, listing.id, version.id

    def _next_version(self, db) -> int:
        return len(db.scalars(select(CvVersion).where(CvVersion.user_id == self.user.id)).all()) + 1

    def _wait_for_document(self, document_id, expected: TailoredDocumentStatus, timeout: int = 20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.Session() as db:
                document = db.get(TailoredDocument, document_id)
                if document and document.status == expected:
                    return document
            time.sleep(0.1)
        raise AssertionError(f"Document {document_id} did not reach {expected}")

    def test_real_worker_processes_idempotency_retry_lease_recovery_and_email(self):
        registered = celery_app.control.inspect(timeout=2).registered() or {}
        registered_names = {name for names in registered.values() for name in names}
        self.assertTrue({
            "app.cv_tailoring.tasks.process_tailored_document",
            "app.cv_tailoring.tasks.reconcile_stale_tailoring",
            "app.applications.tasks.send_application_email",
        }.issubset(registered_names))
        normal_id, normal_candidate, _, normal_version_id = self._reserve("NORMAL")
        self.state.allow_blocked_response.clear()
        self.state.block_candidate_prefixes.add("NORMAL")
        process_tailored_document_task.delay(str(normal_id))
        self.assertTrue(self.state.analysis_started.wait(timeout=15), "worker did not reach synthetic provider")
        self._wait_for_document(normal_id, TailoredDocumentStatus.processing)
        self.state.allow_blocked_response.set()
        normal = self._wait_for_document(normal_id, TailoredDocumentStatus.ready)
        with self.Session() as db:
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == normal_id))
            usage = db.scalar(select(FeatureUsage).where(FeatureUsage.user_id == self.user.id))
            self.assertEqual(reservation.status, ReservationStatus.consumed)
            self.assertEqual(usage.free_uses_count, 1)
            self.assertTrue(normal.tailored_cv_key and normal.cover_letter_key)
        normal_calls = self.state.calls_by_candidate[normal_candidate]
        duplicate_one = process_tailored_document_task.delay(str(normal_id))
        duplicate_two = process_tailored_document_task.delay(str(normal_id))
        duplicate_one.get(timeout=15)
        duplicate_two.get(timeout=15)
        self.assertEqual(self.state.calls_by_candidate[normal_candidate], normal_calls)

        transient_id, transient_candidate, _, _ = self._reserve("TRANSIENT")
        self.state.transient_remaining[transient_candidate] = 1
        process_tailored_document_task.delay(str(transient_id))
        transient = self._wait_for_document(transient_id, TailoredDocumentStatus.ready)
        self.assertEqual(transient.attempt_count, 2)
        with self.Session() as db:
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == transient_id))
            self.assertEqual(reservation.status, ReservationStatus.consumed)

        stale_id, _, _, _ = self._reserve("STALE")
        with self.Session() as db:
            stale = db.get(TailoredDocument, stale_id)
            stale.status = TailoredDocumentStatus.processing
            stale.attempt_count = 3
            stale.processing_lease_expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(reconcile_stale_tailoring.delay().get(timeout=15), 0)
        stale = self._wait_for_document(stale_id, TailoredDocumentStatus.failed)
        with self.Session() as db:
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == stale_id))
            self.assertEqual(reservation.status, ReservationStatus.released)

        with self.Session() as db:
            email_listing = Listing(
                id=uuid.uuid4(), source="celery-test", source_listing_id=str(uuid.uuid4()), title="Email Role",
                description="Synthetic email test", required_skills=[], apply_method=ApplyMethod.email,
                apply_target="synthetic@example.test", listing_type=ListingType.job,
            )
            application = Application(
                user_id=self.user.id, listing_id=email_listing.id, status=ApplicationStatus.prepared,
                submission_status=ApplicationSubmissionStatus.email_queued, applied_via=AppliedVia.phanda_email,
            )
            profile = db.get(Profile, self.user.id)
            profile.active_cv_version_id = normal_version_id
            db.add_all([email_listing, application])
            db.commit()
            application_id = application.id
        first_email = send_application_email_task.delay(str(application_id))
        first_email.get(timeout=15)
        second_email = send_application_email_task.delay(str(application_id))
        second_email.get(timeout=15)
        with self.Session() as db:
            application = db.get(Application, application_id)
            self.assertEqual(application.submission_status, ApplicationSubmissionStatus.email_failed)
            self.assertEqual(application.email_attempt_count, 1)

        crash_id, _, _, _ = self._reserve("CRASH")
        self.state.analysis_started.clear()
        self.state.allow_blocked_response.clear()
        self.state.block_candidate_prefixes.add("CRASH")
        process_tailored_document_task.delay(str(crash_id))
        self.assertTrue(self.state.analysis_started.wait(timeout=15), "worker did not begin crash-recovery task")
        self._wait_for_document(crash_id, TailoredDocumentStatus.processing)
        self._stop_worker()
        self.state.allow_blocked_response.set()
        self._start_worker()
        with self.Session() as db:
            document = db.get(TailoredDocument, crash_id)
            document.processing_lease_expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        reconcile_stale_tailoring.delay().get(timeout=15)
        recovered = self._wait_for_document(crash_id, TailoredDocumentStatus.ready)
        self.assertGreaterEqual(recovered.attempt_count, 2)
        with self.Session() as db:
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == crash_id))
            self.assertEqual(reservation.status, ReservationStatus.consumed)
