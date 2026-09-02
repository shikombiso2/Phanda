# Phanda Backend

FastAPI backend for Phanda, following `phanda-codex-prompt.md` and `phanda-backend-architecture.md`.

## What is included

- Passwordless-free email/password auth (Argon2id hashing) plus server-verified Google Sign-In, linked by email so one person never gets two accounts
- Short-lived access JWTs with revocable, rotating refresh tokens; reuse of a rotated token revokes the whole session family
- Redis-backed rate limiting on register/login/Google/refresh
- Structured JSON logging to stdout; `/health` (liveness) and `/ready` (Postgres/Redis/storage readiness)
- Production boots refuse to start with an unchanged `JWT_SECRET`
- Immutable CV versions with asynchronous PDF/DOCX/TXT extraction
- Normalized listings schema with Adzuna ingestion first
- Explainable skill-overlap matching
- Gemini-backed, provider-neutral structured CV tailoring with deterministic validation and PDF rendering
- Separate tailoring and application flows; email applications use real PDF attachments
- Skill-gap flagging and gated roadmap resources
- Reservation-based tailoring allowance so failed generation does not consume a request
- Single `/webhooks/revenuecat` webhook for entitlements and wallet updates
- Celery beat task for scheduled Adzuna ingestion

## Local setup

1. Install Python 3.12+.
2. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Start Postgres and Redis:

```powershell
docker compose up -d
```

4. Copy environment defaults and fill provider keys as needed:

```powershell
Copy-Item .env.example .env
```

5. Apply the database schema (this project uses Alembic; do not rely on API startup to create tables):

```powershell
alembic upgrade head
```

6. Run the API:

```powershell
uvicorn main:app --reload
```

The API exposes OpenAPI docs at `http://127.0.0.1:8000/docs`.

Seed a local dev user and two sample listings:

```powershell
python -m scripts.seed_dev
```

## Useful commands

Run Adzuna ingestion manually (requires `INGESTION_TRIGGER_SECRET` to be set):

```powershell
curl -X POST http://127.0.0.1:8000/ingestion/adzuna/run -H "X-Ingestion-Secret: $env:INGESTION_TRIGGER_SECRET"
```

Run the Celery worker:

```powershell
celery -A app.celery_app.celery_app worker --loglevel=info
```

Run the Celery beat scheduler:

```powershell
celery -A app.celery_app.celery_app beat --loglevel=info
```

## Notes

- Authentication is email/password and Google Sign-In only — there is no phone number or SMS OTP anywhere in this codebase. Set `GOOGLE_OAUTH_CLIENT_IDS` (comma-separated) to enable `POST /auth/google`; it returns 503 while unset.
- Set `ENVIRONMENT=production` to enable the startup safety check that refuses to boot with the default `JWT_SECRET`.
- Files are uploaded to S3 when `S3_BUCKET` is configured; otherwise development downloads are proxied by the API. Storage URIs are never returned.
- RevenueCat webhook verification expects `X-RevenueCat-Webhook-Signature` with HMAC signing enabled and `REVENUECAT_WEBHOOK_SECRET` set.
- No LinkedIn scraping, custom AdMob SSV, PayFast/Yoco, ML ranking, or automated ATS form submission is implemented.
