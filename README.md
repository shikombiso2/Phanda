# Phanda Backend

FastAPI backend for Phanda, following `phanda-codex-prompt.md` and `phanda-backend-architecture.md`.

## What is included

- Email/password auth (Argon2id hashing) plus server-verified Google Sign-In, linked by email so one person never gets two accounts
- Short-lived access JWTs with revocable, rotating refresh tokens; reuse of a rotated token revokes the whole session family
- Redis-backed rate limiting on register/login/Google/refresh
- Structured JSON logging to stdout; `/health` (liveness) and `/ready` (Postgres/Redis/storage readiness)
- Production boots refuse to start with an unchanged `JWT_SECRET`
- Immutable CV versions with asynchronous PDF/DOCX/TXT extraction
- Normalized listings schema with Adzuna ingestion first
- Cold-start-capable, explainable job matching: a hand-calibrated probabilistic combination of skill/experience/job-type/location/industry/salary compatibility factors (see `docs/RECOMMENDATIONS.md`)
- Limit/offset pagination on every list endpoint (listings, matches, applications, saved opportunities)
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

3. Start Postgres and Redis (infrastructure only -- the API itself runs from your venv with `--reload` in step 6):

```powershell
docker compose up -d postgres redis
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

## Deployment

The whole stack -- API, Celery worker, Celery beat, and a one-shot migration step -- builds from the single `Dockerfile` and runs via `docker-compose.yml`:

```powershell
Copy-Item .env.example .env   # fill in real provider keys and a real JWT_SECRET for anything but local use
docker compose up --build
```

`migrate` runs `alembic upgrade head` once and exits; `api`, `worker`, and `beat` all wait for it to succeed before starting, so nothing races to migrate the database concurrently. Each service reads `.env` for provider credentials but has its `DATABASE_URL`/`REDIS_URL` overridden to point at the `postgres`/`redis` service names rather than `localhost`, since `.env`'s defaults are for running the API from your host machine, not from inside a container.

For an actual production deployment (a managed host, not just `docker compose`): build the same image, run `alembic upgrade head` as your release/migration step, run `api`/`worker`/`beat` as separate long-running processes from it, and set `ENVIRONMENT=production` plus a real `JWT_SECRET` -- the app refuses to start otherwise. `--proxy-headers --forwarded-allow-ips` on the API command matters if you're behind a reverse proxy or load balancer: without it, the rate limiter's per-IP keys would all resolve to the proxy's own address instead of the real client.

CI (`.github/workflows/ci.yml`) runs the full test suite, including the PostgreSQL- and Redis-gated integration tests, against real service containers on every push and pull request.
