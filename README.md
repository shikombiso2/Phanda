# Phanda Backend

FastAPI backend for Phanda, following `phanda-codex-prompt.md` and `phanda-backend-architecture.md`.

## What is included

- Phone + OTP auth with JWT issuance
- JWT refresh endpoint
- Optional generic SMS delivery hook for production OTP sending
- Profile CRUD and CV upload path storage
- Normalized listings schema with Adzuna ingestion first
- Explainable skill-overlap matching
- CV and cover-letter tailoring through Anthropic, with local fallback when no API key is set
- Application tracking for email and ATS-link listings
- Skill-gap flagging and gated roadmap resources
- Unified `check_access(user_id, feature_key)` gate for CV tailoring and skill-gap roadmap
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

5. Run the API:

```powershell
uvicorn main:app --reload
```

The API will create MVP tables on startup and expose OpenAPI docs at `http://127.0.0.1:8000/docs`.

Seed a local dev user and two sample listings:

```powershell
python scripts/seed_dev.py
```

## Useful commands

Run Adzuna ingestion manually:

```powershell
curl -X POST http://127.0.0.1:8000/ingestion/adzuna/run
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

- `OTP_DEV_MODE=true` returns the OTP in the response for local testing.
- Set `OTP_DEV_MODE=false`, `SMS_API_URL`, and `SMS_API_KEY` to send OTPs through a configured SMS gateway.
- Files are uploaded to S3 when `S3_BUCKET` is configured; otherwise the app returns `local://...` placeholders.
- RevenueCat webhook verification expects `X-RevenueCat-Webhook-Signature` with HMAC signing enabled and `REVENUECAT_WEBHOOK_SECRET` set.
- No LinkedIn scraping, custom AdMob SSV, PayFast/Yoco, ML ranking, or automated ATS form submission is implemented.
