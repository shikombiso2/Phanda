"""Run only when PHANDA_RUN_POSTGRES_INTEGRATION=1 is explicitly set."""
from __future__ import annotations

import os
import threading
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import (
    Application, ApplicationStatus, ApplicationSubmissionStatus, ApplyMethod, CvVersion, CvVersionStatus,
    ExperienceLevel, FeatureUsage, JobType, Listing, ListingType,
    Profile, ReservationSource, ReservationStatus, TailoredDocument, TailoredDocumentStatus,
    TailoringRequestReservation, User, Wallet, utcnow,
)
from app.app_factory import create_app
from app.core.db import get_db
from app.core.security import get_current_user
from app.monetization.gate import consume_reservation, release_reservation, reserve_tailoring_request
from app.cv_tailoring.schemas import AnalysisPlan, CandidateFact, CandidateFacts, CvClaim, CvSection, JobRequirements, MatchingStrategy, SourceSpan, TailoredCv
from app.cv_tailoring.service import fail_stale_documents, process_tailored_document
from tests.postgres_harness import PostgresHarness


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class ReservationPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = PostgresHarness()
        cls.harness.create()
        cls.engine = create_engine(cls.harness.test_url, pool_size=8, max_overflow=0)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.harness.drop()

    def setUp(self):
        with self.Session() as db:
            user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            profile = Profile(user_id=user.id, job_type=JobType.any, experience_level=ExperienceLevel.none, skills=[], industries=[])
            cv = CvVersion(
                id=uuid.uuid4(), user_id=user.id, version_number=1, status=CvVersionStatus.ready,
                storage_key=f"test/{uuid.uuid4()}.txt", filename="cv.txt", content_type="text/plain", byte_size=100,
                sha256=uuid.uuid4().hex * 2, extracted_text_key="test/extracted.txt", ready_at=utcnow(),
            )
            db.add_all([user, profile])
            db.flush()
            db.add(cv)
            db.commit()
            self.user_id, self.cv_id = user.id, cv.id

    def _listing(self, db: Session) -> Listing:
        listing = Listing(
            id=uuid.uuid4(), source="test", source_listing_id=str(uuid.uuid4()), title="Developer", description="Python role",
            required_skills=["Python"], apply_method=ApplyMethod.ats_link, apply_target="https://example.test/apply", listing_type=ListingType.job,
        )
        db.add(listing)
        db.commit()
        return listing

    def _reserve(self, listing_id: uuid.UUID, key: str):
        with self.Session() as db:
            return reserve_tailoring_request(
                db, user_id=self.user_id, listing=db.get(Listing, listing_id), profile=db.get(Profile, self.user_id),
                cv_version=db.get(CvVersion, self.cv_id), idempotency_key=key,
            )

    def test_one_remaining_two_simultaneous_requests_reserve_once(self):
        with self.Session() as db:
            listing = self._listing(db)
            db.add(FeatureUsage(user_id=self.user_id, feature_key="cv_tailor", period_start=utcnow().date().replace(day=1), free_uses_count=2))
            db.commit()
        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker(key):
            try:
                barrier.wait()
                results.append(self._reserve(listing.id, key))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"request-{index:08d}",)) for index in range(2)]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(len(errors), 0)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(TailoringRequestReservation.id)).where(TailoringRequestReservation.user_id == self.user_id)), 1)
            usage = db.scalar(select(FeatureUsage).where(FeatureUsage.user_id == self.user_id))
            self.assertEqual(usage.free_uses_count, 2)

    def test_three_remaining_four_concurrent_listings_reserve_exactly_three(self):
        with self.Session() as db:
            listings = [self._listing(db) for _ in range(4)]
        barrier = threading.Barrier(4)
        results, errors = [], []

        def worker(index):
            try:
                barrier.wait()
                results.append(self._reserve(listings[index].id, f"parallel-{index:07d}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        self.assertEqual(sum(result.created for result in results), 3)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], PermissionError)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(TailoringRequestReservation.id)).where(TailoringRequestReservation.user_id == self.user_id)), 3)

    def test_consumption_release_and_retry_are_idempotent(self):
        with self.Session() as db:
            listing = self._listing(db)
        created = self._reserve(listing.id, "first-key")
        with self.Session() as db:
            document = db.get(TailoredDocument, created.document.id)
            consume_reservation(db, document)
            consume_reservation(db, document)
            db.commit()
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == document.id))
            self.assertEqual(reservation.status, ReservationStatus.consumed)
            self.assertEqual(db.scalar(select(FeatureUsage.free_uses_count).where(FeatureUsage.user_id == self.user_id)), 1)
            release_reservation(db, document)
            db.commit()
            self.assertEqual(reservation.status, ReservationStatus.consumed)

        with self.Session() as db:
            retry_listing = self._listing(db)
        failed = self._reserve(retry_listing.id, "failed-key")
        with self.Session() as db:
            document = db.get(TailoredDocument, failed.document.id)
            document.status = TailoredDocumentStatus.failed
            release_reservation(db, document)
            release_reservation(db, document)
            db.commit()
        retry = self._reserve(retry_listing.id, "retry-key")
        self.assertTrue(retry.created)
        self.assertEqual(retry.document.id, failed.document.id)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(TailoringRequestReservation.id)).where(TailoringRequestReservation.tailored_document_id == failed.document.id),), 1)

    def test_releasing_a_rewarded_reservation_refunds_a_brand_new_wallet(self):
        """Regression test: release_reservation's `if not wallet: wallet =
        Wallet(...)` branch used to omit `balance=0`. SQLAlchemy's
        column-level default is applied at flush/INSERT time, not at
        construction, so `wallet.balance` was still None in memory and the
        following `wallet.balance += 1` raised TypeError -- but only for a
        user's *first ever* rewarded-tailoring wallet transaction, which no
        existing test exercised (every other reservation test here uses the
        free-quota path). Verified failing against real PostgreSQL before
        this fix existed."""
        with self.Session() as db:
            listing = self._listing(db)
            # Exhaust free quota so reserve_tailoring_request must fall back
            # to the rewarded-credit source.
            db.add(FeatureUsage(user_id=self.user_id, feature_key="cv_tailor", period_start=utcnow().date().replace(day=1), free_uses_count=3))
            db.add(Wallet(user_id=self.user_id, currency_key="tailoring_requests", balance=1))
            db.commit()

        reserved = self._reserve(listing.id, "rewarded-release-key")
        with self.Session() as db:
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == reserved.document.id))
            self.assertEqual(reservation.source, ReservationSource.rewarded)
            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id, Wallet.currency_key == "tailoring_requests"))
            self.assertEqual(wallet.balance, 0, "the rewarded credit should have been spent on reservation")

            document = db.get(TailoredDocument, reserved.document.id)
            document.status = TailoredDocumentStatus.failed
            release_reservation(db, document)  # must not raise
            db.commit()

            wallet = db.scalar(select(Wallet).where(Wallet.user_id == self.user_id, Wallet.currency_key == "tailoring_requests"))
            self.assertEqual(wallet.balance, 1, "a released rewarded reservation must refund the spent credit")

    def test_retrying_a_failed_rewarded_reservation_refunds_before_re_reserving(self):
        """Same bug, the other call site: _release_existing_reservation
        (invoked when reserve_tailoring_request retries a failed/cancelled
        document). Deletes the wallet row entirely between the first
        reservation and the retry so the retry hits the same
        wallet-does-not-exist-yet branch as a first-time user."""
        with self.Session() as db:
            listing = self._listing(db)
            db.add(FeatureUsage(user_id=self.user_id, feature_key="cv_tailor", period_start=utcnow().date().replace(day=1), free_uses_count=3))
            db.add(Wallet(user_id=self.user_id, currency_key="tailoring_requests", balance=1))
            db.commit()

        first = self._reserve(listing.id, "rewarded-retry-key-1")
        with self.Session() as db:
            document = db.get(TailoredDocument, first.document.id)
            document.status = TailoredDocumentStatus.failed
            db.execute(Wallet.__table__.delete().where(Wallet.user_id == self.user_id, Wallet.currency_key == "tailoring_requests"))
            db.commit()

        retried = self._reserve(listing.id, "rewarded-retry-key-2")  # must not raise
        self.assertTrue(retried.created)
        with self.Session() as db:
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == retried.document.id))
            self.assertEqual(reservation.source, ReservationSource.rewarded)

    def test_stale_lease_requeues_or_releases_once(self):
        with self.Session() as db:
            listing = self._listing(db)
        result = self._reserve(listing.id, "stale-key")
        with self.Session() as db:
            document = db.get(TailoredDocument, result.document.id)
            document.status = TailoredDocumentStatus.processing
            document.processing_lease_expires_at = utcnow() - timedelta(minutes=1)
            document.attempt_count = 0
            db.commit()
            self.assertEqual(fail_stale_documents(db), [str(document.id)])
            self.assertEqual(document.status, TailoredDocumentStatus.queued)
            document.status = TailoredDocumentStatus.processing
            document.processing_lease_expires_at = utcnow() - timedelta(minutes=1)
            document.attempt_count = 3
            db.commit()
            fail_stale_documents(db)
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == document.id))
            self.assertEqual(document.status, TailoredDocumentStatus.failed)
            self.assertEqual(reservation.status, ReservationStatus.released)

    def test_duplicate_pipeline_execution_does_not_regenerate_or_double_consume(self):
        source_text = "Python Developer 2 years"
        source_fact = CandidateFact(id="fact_1", category="experience", normalized_value=source_text, source_spans=[SourceSpan(start=0, end=len(source_text), excerpt=source_text)], confidence=1)
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text=source_text, source_fact_ids=["fact_1"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python", source_fact_ids=["fact_1"])]),
            ], cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_1"])]
        )

        class Provider:
            name = "test"
            model_name = "test-model"
            analyses = 0
            generations = 0

            async def analyze_and_plan(self, *_):
                self.analyses += 1
                return AnalysisPlan(candidate_facts=CandidateFacts(facts=[source_fact]), job_requirements=JobRequirements(), strategy=MatchingStrategy())

            async def generate(self, *_):
                self.generations += 1
                return draft

            async def revise(self, *_):
                raise AssertionError("valid draft must not be corrected")

        with self.Session() as db:
            listing = self._listing(db)
        reserved = self._reserve(listing.id, "pipeline-key")
        provider = Provider()
        with patch("app.cv_tailoring.service.get_tailoring_provider", return_value=provider), \
             patch("app.cv_tailoring.service.get_bytes", return_value=source_text.encode()), \
             patch("app.cv_tailoring.service.put_bytes", side_effect=lambda _data, key, _type: key), \
             patch("app.cv_tailoring.service.render_cv_pdf", return_value=b"pdf"), \
             patch("app.cv_tailoring.service.render_cover_letter_pdf", return_value=b"pdf"):
            with self.Session() as db:
                process_tailored_document(db, reserved.document.id)
                process_tailored_document(db, reserved.document.id)
        with self.Session() as db:
            document = db.get(TailoredDocument, reserved.document.id)
            reservation = db.scalar(select(TailoringRequestReservation).where(TailoringRequestReservation.tailored_document_id == document.id))
            self.assertEqual(document.status, TailoredDocumentStatus.ready)
            self.assertEqual(reservation.status, ReservationStatus.consumed)
            self.assertEqual(db.scalar(select(FeatureUsage.free_uses_count).where(FeatureUsage.user_id == self.user_id)), 1)
        self.assertEqual(provider.analyses, 1)
        self.assertEqual(provider.generations, 1)


@unittest.skipUnless(os.getenv("PHANDA_RUN_POSTGRES_INTEGRATION") == "1", "requires explicit disposable PostgreSQL integration run")
class TailoringAuthorizationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.harness = PostgresHarness()
        cls.harness.create()
        cls.engine = create_engine(cls.harness.test_url)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)
        cls.app = create_app()

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        cls.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.app.dependency_overrides.clear()
        cls.client.close()
        cls.engine.dispose()
        cls.harness.drop()

    def setUp(self):
        with self.Session() as db:
            self.user_a = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            self.user_b = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:12]}@example.test")
            profile_a = Profile(user_id=self.user_a.id, job_type=JobType.any, experience_level=ExperienceLevel.none, skills=[], industries=[])
            profile_b = Profile(user_id=self.user_b.id, job_type=JobType.any, experience_level=ExperienceLevel.none, skills=[], industries=[])
            db.add_all([self.user_a, self.user_b, profile_a, profile_b])
            db.flush()
            self.cv_a = self._cv(self.user_a.id)
            self.cv_b = self._cv(self.user_b.id)
            db.add_all([self.cv_a, self.cv_b])
            db.flush()
            profile_a.active_cv_version_id, profile_b.active_cv_version_id = self.cv_a.id, self.cv_b.id
            self.ats_listing = self._listing(ApplyMethod.ats_link)
            self.email_listing = self._listing(ApplyMethod.email)
            self.manual_listing = self._listing(ApplyMethod.manual)
            db.add_all([self.ats_listing, self.email_listing, self.manual_listing])
            db.flush()
            self.document_b = self._ready_document(self.user_b.id, self.ats_listing.id, self.cv_b.id)
            self.document_a = self._ready_document(self.user_a.id, self.ats_listing.id, self.cv_a.id)
            db.add_all([self.document_b, self.document_a])
            db.commit()
        self.app.dependency_overrides[get_current_user] = lambda: self.user_a

    def _cv(self, user_id):
        return CvVersion(id=uuid.uuid4(), user_id=user_id, version_number=1, status=CvVersionStatus.ready, storage_key=f"test/{uuid.uuid4()}.txt", filename="cv.txt", content_type="text/plain", byte_size=100, sha256=uuid.uuid4().hex * 2, extracted_text_key="test/extracted.txt", ready_at=utcnow())

    def _listing(self, method):
        if method == ApplyMethod.email:
            apply_target = "employer@example.test"
        elif method == ApplyMethod.manual:
            apply_target = "Submit a Z83 form to the address in the description."
        else:
            apply_target = "https://example.test/apply"
        return Listing(id=uuid.uuid4(), source="test", source_listing_id=str(uuid.uuid4()), title="Developer", description="Python role", required_skills=["Python"], apply_method=method, apply_target=apply_target, listing_type=ListingType.job)

    def _ready_document(self, user_id, listing_id, cv_id):
        return TailoredDocument(id=uuid.uuid4(), user_id=user_id, listing_id=listing_id, cv_version_id=cv_id, status=TailoredDocumentStatus.ready, tailored_cv_key="test/cv.pdf", cover_letter_key="test/cover.pdf", output_format="pdf", listing_snapshot_json={}, profile_snapshot_json={}, prompt_version="v1", idempotency_key=str(uuid.uuid4()), input_fingerprint=uuid.uuid4().hex * 2, attempt_count=1, correction_attempted=False, ready_at=utcnow())

    def test_cross_user_document_endpoints_and_random_ids_are_not_disclosed(self):
        document_id = str(self.document_b.id)
        self.assertEqual(self.client.get(f"/tailored-documents/{document_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/tailored-documents/{document_id}/download").status_code, 404)
        self.assertEqual(self.client.post(f"/tailored-documents/{document_id}/email").status_code, 404)
        self.assertEqual(self.client.get(f"/tailored-documents/{uuid.uuid4()}").status_code, 404)

    def test_authorized_signed_download_reports_the_actual_five_minute_expiry(self):
        with patch("app.cv_tailoring.router.create_download_url", return_value="https://storage.example/signed") as signer:
            response = self.client.get(f"/tailored-documents/{self.document_a.id}/download")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "https://storage.example/signed")
        expires_at = datetime.fromisoformat(response.json()["expires_at"])
        remaining_seconds = (expires_at - datetime.now(expires_at.tzinfo)).total_seconds()
        self.assertGreater(remaining_seconds, 295)
        self.assertLessEqual(remaining_seconds, 300)
        self.assertEqual(signer.call_args.kwargs["expires_in"], 300)

    def test_user_cannot_select_another_users_cv_or_document(self):
        response = self.client.post("/tailored-documents", json={"listing_id": str(self.ats_listing.id), "cv_version_id": str(self.cv_b.id)}, headers={"Idempotency-Key": "security-cv-key"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(f"/applications/{self.ats_listing.id}/apply", json={"tailored_document_id": str(self.document_b.id)}, headers={"Idempotency-Key": "security-application-key"})
        self.assertEqual(response.status_code, 409)

    def test_client_cannot_supply_employer_address(self):
        with patch("app.applications.tasks.send_application_email_task.delay") as enqueue:
            response = self.client.post(f"/applications/{self.email_listing.id}/apply", json={"employer_email": "attacker@example.test"}, headers={"Idempotency-Key": "trusted-target-key"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(enqueue.call_count, 1)
        with self.Session() as db:
            self.assertEqual(db.get(Listing, self.email_listing.id).apply_target, "employer@example.test")

    def test_manual_apply_method_prepares_with_no_email_and_shows_the_target(self):
        # DPSA-style listing: no automated submission path exists at all.
        # Must not claim a click-through happened (external_started) and
        # must not send an email -- the user completes this themselves,
        # entirely outside Phanda.
        with patch("app.applications.tasks.send_application_email_task.delay") as enqueue:
            response = self.client.post(f"/applications/{self.manual_listing.id}/apply", headers={"Idempotency-Key": "manual-apply-key"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(enqueue.call_count, 0)
        body = response.json()
        self.assertEqual(body["apply_method"], "manual")
        self.assertEqual(body["apply_target"], "Submit a Z83 form to the address in the description.")
        self.assertEqual(body["status"], "prepared")
        with self.Session() as db:
            application = db.scalar(select(Application).where(Application.listing_id == self.manual_listing.id))
            self.assertEqual(application.status, ApplicationStatus.prepared)
            self.assertEqual(application.submission_status, ApplicationSubmissionStatus.not_started)

    def test_reused_idempotency_key_across_different_listings_creates_two_applications(self):
        # The dedup check used to match on (user_id, idempotency_key) alone,
        # so reusing a key across two different listings would silently
        # return the FIRST listing's application for the second apply --
        # no new row, no error, just the wrong application handed back.
        # Widened to (user_id, listing_id, idempotency_key): a shared key is
        # only a duplicate for the SAME listing.
        shared_key = "shared-key-reused-across-listings"
        first = self.client.post(f"/applications/{self.ats_listing.id}/apply", headers={"Idempotency-Key": shared_key})
        self.assertEqual(first.status_code, 202)
        second = self.client.post(f"/applications/{self.manual_listing.id}/apply", headers={"Idempotency-Key": shared_key})
        self.assertEqual(second.status_code, 202)

        self.assertNotEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(first.json()["listing_id"], str(self.ats_listing.id))
        self.assertEqual(second.json()["listing_id"], str(self.manual_listing.id))

        with self.Session() as db:
            applications = db.scalars(
                select(Application).where(Application.user_id == self.user_a.id, Application.idempotency_key == shared_key)
            ).all()
            self.assertEqual(len(applications), 2)
            self.assertEqual({a.listing_id for a in applications}, {self.ats_listing.id, self.manual_listing.id})
