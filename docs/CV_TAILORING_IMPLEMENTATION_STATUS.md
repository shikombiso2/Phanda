# CV tailoring implementation status

## Current status (2026-08-31)

The CV-tailoring MVP has a working provider-neutral Gemini pipeline and public API surface, but it is not production-complete. Alembic is now configured with a single additive revision for the established legacy schema. It has been verified only on a disposable copy of the live schema; the live `phanda` database remains unmigrated. API startup no longer invokes `create_all`, preventing accidental partial production schema changes before migration.

## Complete

- CV version model and active CV pointer, preserving version-specific tailored documents.
- PDF, DOCX and UTF-8 TXT validation/extraction in Celery, including file/page limits, encrypted PDF rejection and scanned-PDF detection.
- Provider protocol and Gemini REST adapter with schema-constrained JSON, server-owned instructions and prompt-injection boundaries.
- Two-call analysis/generation pipeline, deterministic provenance checks, one constrained correction attempt, controlled ReportLab PDF rendering, private storage keys and processing leases.
- Reservation ledger, read-only allowance endpoint, final-success consumption and permanent-failure release.
- `POST /tailored-documents`, `GET /tailored-documents/{id}`, signed/proxied private download, and email retry API.
- Application creation no longer generates a tailored CV. Email applications are queued and attach file bytes rather than storage URLs; ATS applications only record that the external flow started.
- RevenueCat tailoring reward events are ledgered and replay-safe when a verified event has an ID.
- Additive Alembic revision `20260831_add_cv_tailoring` adds only CV-tailoring tables/columns/types and has passed upgrade, structural inspection, downgrade, and re-upgrade on isolated PostgreSQL databases.
- Application idempotency has a database-level unique constraint and unknown email provider outcomes are not retried automatically.
- PII-safe structured event logging now covers request/reservation, worker start/completion/failure, provider latency/error, validation/correction, lease release, download, email, and reward outcomes. Payloads reject dictionaries/lists to avoid accidental CV/prompt/provider-response logging.
- The documented Celery worker now imports and registers ingestion, tailoring, and email task modules. It uses late acknowledgement and rejects lost worker tasks so lease-protected work can be redelivered after a worker crash.
- Master CV applications remain supported: PDF uploads are attached directly, while ready DOCX/TXT uploads are rendered to a PDF from their extracted text before email. Private storage URIs are never attached or sent.
- Signed-download responses report the same five-minute expiry used when creating the S3 URL.

## Partially complete

- Retry/reconciliation exists and passed direct PostgreSQL integration tests. Worker task registration and at-least-once acknowledgement configuration have unit coverage, but still need an actual Celery-worker/Redis delivery test.
- Validation checks source spans, fact references, required sections, metrics/dates, named employers, selected job titles and qualifications, and skills-section claims. It still needs broader domain-aware provenance coverage.
- Retry/reconciliation and email outcome handling have focused unit coverage, but need actual Celery-worker integration coverage.

## Remaining / known issues

- Add actual Celery-worker/Redis duplicate-delivery and crash-recovery tests, plus S3/Gemini/email-provider end-to-end tests. In the current environment Redis is configured for `localhost:6379` but is not listening; Docker and Redis CLI are unavailable.
- Add a documented server-side verified rewarded-ad webhook if RevenueCat virtual currency is not the reward source, and connect the existing structured events to the production log/metrics sink.
- Expand API-level extraction tests and provider adversarial corpus coverage beyond the current unit contracts.
- Backfill usable legacy `profiles.cv_file_url` records only after validating their backing object; do not backfill `local://` placeholders.

## Files changed / added

Core implementation spans `app/core/models.py`, `app/core/storage.py`, `app/profiles/router.py`, `app/monetization/gate.py`, `app/cv_tailoring/`, `app/applications/`, and `app/monetization/revenuecat_webhook.py`. This session also added `alembic.ini`, `migrations/`, and `scripts/verify_cv_tailoring_migration.py`; replaced a guessed baseline artifact with an additive-only migration; reconciled a legacy ORM constraint; expanded deterministic validation; and made email timeout outcomes non-retryable.

## Verification

- Passing: `.venv\\Scripts\\python.exe -m unittest discover -v` (42 tests, 9 PostgreSQL tests skipped by default), `.venv\\Scripts\\python.exe -m compileall -q app tests scripts`, and `git diff --check`.
- Passing: `.venv\\Scripts\\python.exe -m unittest tests.test_postgres_tailoring_integration -q` with `PHANDA_RUN_POSTGRES_INTEGRATION=1` (9/9). It created, migrated, and removed disposable `phanda_integration_test_*` databases only. This verifies both stated reservation-contention cases, idempotent consume/release/retry, stale leases, duplicate pipeline execution, cross-user authorization paths, and the authorized five-minute signed-download expiry.
- Passing: `.venv\\Scripts\\python.exe -m scripts.verify_cv_tailoring_migration --database phanda_migration_test_audit`; it upgraded, inspected, downgraded, re-upgraded, then removed a disposable database. The source database was read-only.
- Passing with mocks/local test storage only: S3 key validation, local private storage, five-minute presign arguments, Gemini response/error contracts, SendGrid attachment payloads, and email timeout handling. No real provider request was sent.
- Verified read-only on live `phanda`: it contains the legacy nine tables; no CV-tailoring tables, new columns, new enums, or `alembic_version` table exist. The live database was not modified.
- Not run: live Celery/Redis worker delivery, S3, Gemini, and email-provider integration.

## Next recommended step

Before an explicit production migration approval, take a database backup and review the generated SQL with the deployment operator. The next engineering step is to make a disposable Redis instance available and run a real Celery worker test for duplicate delivery, crash recovery, and retry scheduling; no production migration should be run as part of that work.
