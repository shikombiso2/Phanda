# Phanda — Backend Architecture (MVP)

**Platform:** Android, Google Play Store
**Monetization SDK:** RevenueCat (in-app purchases + RevenueCat Ads) — required for Shipaton 2026 eligibility
**Deadline constraint:** First public Play Store listing must go live between Aug 1 – Sep 30, 2026 to qualify for Shipaton. Confirm this against your own hackathon deadline before finalizing the build schedule.

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| API framework | **Python + FastAPI** | Auto-generated OpenAPI docs (frontend/Claude Code can consume the exact contract), strong fit for the AI-calling parts of the app (CV tailoring, matching) |
| Database | **PostgreSQL** | Relational data — users, listings, applications, entitlements all reference each other cleanly |
| Background jobs | **Celery + Redis** (or `arq` for a lighter footprint) | Scraping runs on a schedule, not per-request; CV generation may be slow enough to run async |
| File storage | **S3-compatible object storage** (AWS S3 or Backblaze B2) | Generated CVs/cover letters, uploaded CVs. Never store binary files in Postgres. |
| Auth | **JWT**, phone number + OTP as primary login | Matches your target user's likely primary channel; needs an SMS provider (Twilio, or a local SA provider like Clickatell/BulkSMS for cheaper local delivery) |
| Transactional email | **SendGrid or Mailgun** | Used to send applications on the user's behalf for email-apply listings |
| Monetization | **RevenueCat SDK** (client) + **RevenueCat webhooks** (server) | Handles Google Play Billing, entitlements, and ad-reward verification — see Section 5 |
| LLM | **Anthropic API (Claude)** | CV/cover letter tailoring |

---

## 2. Data Model (core tables)

```
users
- id
- phone_number (unique)
- email (nullable)
- created_at

profiles
- user_id (FK)
- job_type            (full_time | part_time | internship | learnership | any)
- location
- open_to_remote      (bool)
- skills              (array or join table — see note below)
- industries           (array)
- education_level
- experience_level     (none | some | experienced)
- desired_salary_min
- desired_salary_max
- cv_file_url          (nullable, S3 path)
- profile_completeness (int, 0-100, computed)

listings
- id
- source                ("adzuna" | "graduates24" | "gov_vacancies" | ...)
- source_listing_id      (external ID, for de-duping on re-ingest)
- title
- company
- location
- listing_type           (job | internship | learnership | apprenticeship | bursary)
- salary_min / salary_max (nullable)
- description
- required_skills         (array — parsed/tagged at ingestion)
- apply_method            ("ats_link" | "email")
- apply_target             (URL if ats_link, email address if email)
- posted_at
- ingested_at
- is_active               (bool — for expiring stale listings)

applications
- id
- user_id (FK)
- listing_id (FK)
- status                 (applied | interview | offer | rejected | withdrawn) — MVP only needs "applied" as a real state; others are stretch
- tailored_cv_url         (nullable, S3 path)
- tailored_cover_letter_url (nullable)
- applied_via             ("phanda_email" | "external_link")
- applied_at

saved_opportunities
- user_id (FK)
- listing_id (FK)
- saved_at

feature_usage
- user_id (FK)
- feature_key             ("cv_tailor" | "skill_gap_roadmap")
- period_start             (first of current month)
- free_uses_count
- ad_reward_date           (date — resets daily gate)
- ad_reward_used_today     (bool)

entitlements   -- mirrors RevenueCat state locally, updated via webhook
- user_id (FK)
- entitlement_key          ("phanda_premium")
- is_active                (bool)
- revenuecat_customer_id
- updated_at

wallet   -- mirrors RevenueCat virtual currency balance, updated via webhook
- user_id (FK)
- currency_key             ("boost_tokens")
- balance
- updated_at
```

Note on `skills` / `required_skills`: for MVP, a simple text array or comma-separated tags is fine. A normalized skills taxonomy table is a nice-to-have, not a requirement — don't over-build this before you have real data volume to justify it.

---

## 3. Listings Ingestion — dual source, single normalized schema

This is the most important architectural decision in the whole backend: **every source feeds into the same `listings` table with the same shape**, regardless of whether it came from an API or a scraper. Nothing downstream (matching, display, apply flow) should ever need to know or care where a listing originated.

**Source 1 — Adzuna API.** Real, free, structured public API with South Africa coverage (`country=za`). Provides title, company, location, salary, category, and a direct apply link. Rate-limited on the free tier — build the ingestion job to respect that (scheduled pull, not real-time per-request calls). Register for a free App ID + App Key at the Adzuna developer portal before building this.

**Source 2 — Scraping (Graduates24 and others).** Build each site's scraper as its own small, isolated module that outputs the same normalized shape as the Adzuna adapter. Respect `robots.txt`, keep request rates polite, don't scrape anything behind a login. Government vacancy circulars and NGO/youth-programme boards are good additional low-risk sources — avoid LinkedIn entirely (actively fights automation).

**Ingestion pipeline (Celery scheduled task, e.g. every few hours):**
1. Pull/scrape raw listings from each source
2. Normalize into the shared schema
3. Classify `apply_method`: if the listing's apply instruction is a URL → `ats_link`; if it's an email address → `email`
4. De-dupe against `source_listing_id`
5. Tag `required_skills` — simple keyword extraction against a known skills list is sufficient for MVP; don't build an NLP pipeline for this yet
6. Mark listings not seen in the latest pull as `is_active = false` after a grace period

---

## 4. Core Services

**Auth service** — phone/OTP → JWT issuance and refresh.

**Profile service** — CRUD for the fields captured during registration/profiling. Computes `profile_completeness` for the "Build Your Profile" card.

**Matching service** — computes a match score between a user's profile and a listing. MVP version: keyword/tag overlap between `profile.skills` and `listing.required_skills`, weighted simply (e.g. % of required skills present). Do not build a full ML ranking model for MVP — a transparent, explainable score is actually a *better* product fit here anyway, since your whole differentiation is showing users *why* they match, not just a black-box percentage.

**CV tailoring service** — takes `profile` + a specific `listing`, calls the Anthropic API to generate a tailored CV and cover letter, stores results in S3, links them to the `applications` row. Every call to this service must first pass through the usage-gate (Section 6) before hitting the LLM — the LLM call costs you money per generation, so the gate check happens server-side, before generation, not client-side.

**Applications/tracking service:**
- For `apply_method = "email"` listings: on confirmed apply, sends the tailored CV/cover letter via SendGrid/Mailgun from a Phanda-controlled sending address to the listing's target email. Requires proper SPF/DKIM/DMARC setup on your sending domain before launch — without it, employer mail servers may flag or drop the mail silently, which would break this feature invisibly.
- For `apply_method = "ats_link"` listings: no submission automation. The app hands the user the tailored CV/cover letter and a direct link to the employer's application page; the user completes the final step themselves.
- Both paths record an `applications` row so the user's tracker reflects it either way.

**Skill-gap / "Close the Gap" service** — for MVP, this can be a simple lookup: cross-reference the user's missing skills (from matching output) against a small hardcoded table mapping skill → 2-3 free/low-cost course or learnership links. No need for anything more sophisticated at this stage.

---

## 5. Monetization Architecture — RevenueCat (Purchases + Ads)

### 5.1 Entitlement model

Keep it simple for MVP: **one entitlement, `phanda_premium`**, that unlocks unlimited CV tailoring AND the full skill-gap roadmap together. Don't build separate paywalls per feature yet — one premium tier is easier to build, market, and reason about, and you can split it later once you have usage data showing which feature actually drives upgrades.

### 5.2 Free quota (your own backend, not RevenueCat's job)

RevenueCat has no concept of "3 free uses per month" — that's ordinary app-usage logic, tracked in your own `feature_usage` table. This part of the gate is entirely yours to build.

### 5.3 Ad-reward top-up (RevenueCat Ads — you configure, you don't build)

This is the part that changes significantly from a naive implementation:

1. In the RevenueCat dashboard, connect your AdMob account and create a rewarded ad unit.
2. Configure a **virtual currency** (e.g. `boost_tokens`) that the ad unit grants on completion — e.g. 1 token per watched ad.
3. Enable AdMob **Server-Side Verification (SSV)** on that ad unit, pointing at RevenueCat's SSV callback URL (RevenueCat's docs walk through the exact AdMob console setting).
4. In your Android app, load and show the rewarded ad using RevenueCat's `loadAndTrack` wrapper around the standard AdMob SDK call.
5. When the user completes the ad, AdMob fires the SSV callback to RevenueCat directly — **not to your backend**. RevenueCat verifies it and credits the `boost_tokens` balance server-side. This cannot be spoofed by a tampered client, because your backend is never the thing trusting a client-reported "ad finished" event.
6. RevenueCat sends **your backend** a webhook (`VIRTUAL_CURRENCY_TRANSACTION` or similar) when the balance changes. Your webhook handler updates the local `wallet` table to mirror it.

**What you still need to build yourselves, on top of this:** the "once per day" cap on *offering* the ad at all. RevenueCat's virtual currency has no built-in daily limit — a user could technically watch multiple rewarded ads back to back unless you gate the *display* of the "watch ad" button yourself. Your `feature_usage.ad_reward_date` / `ad_reward_used_today` fields (Section 2) are what enforce this — check them before showing the ad option, independent of RevenueCat.

### 5.4 Webhook handler (single endpoint, handles everything)

Build **one** RevenueCat webhook endpoint that handles all relevant event types:

- `INITIAL_PURCHASE` / `RENEWAL` / `CANCELLATION` → update `entitlements.is_active` for `phanda_premium`
- Virtual currency events → update `wallet.balance` for `boost_tokens`

Always verify the webhook's authenticity (RevenueCat signs webhook payloads) before trusting it.

### 5.5 The unified gate logic

This is the single most important instruction for whoever builds this: **build one `check_access(user_id, feature_key)` function, and have both CV tailoring and skill-gap roadmap call it. Do not duplicate this logic per feature.**

```
check_access(user_id, feature_key):
  1. entitlements.is_active for "phanda_premium"?  → ALLOW, unlimited
  2. feature_usage.free_uses_count < monthly_free_cap for feature_key?
       → ALLOW, increment free_uses_count
  3. wallet.balance for "boost_tokens" > 0
     AND feature_usage.ad_reward_date != today
       → offer "watch an ad for one more" in the UI
       → on confirmed watch (RevenueCat/AdMob flow completes, wallet.balance
         reflects the grant via webhook), spend 1 token, set
         ad_reward_date = today, ad_reward_used_today = true, ALLOW once
  4. Otherwise → BLOCK, trigger the RevenueCat paywall UI for "phanda_premium"
```

---

## 6. Suggested API surface (high-level)

```
POST   /auth/otp/request
POST   /auth/otp/verify

GET    /profile
PUT    /profile
POST   /profile/cv-upload

GET    /listings                  (filtered: type, location, remote, etc.)
GET    /listings/{id}
GET    /listings/matches          (personalized, scored against current profile)

POST   /applications/{listing_id}/apply     (triggers gate check → CV tailoring → send/deep-link)
GET    /applications

POST   /saved-opportunities/{listing_id}
DELETE /saved-opportunities/{listing_id}
GET    /saved-opportunities

GET    /skill-gap                 (flagged gaps, free)
POST   /skill-gap/roadmap/{skill} (gated — full roadmap + resources)

POST   /webhooks/revenuecat       (single handler, see 5.4)
```

---

## 7. Suggested repo structure

```
/app
  /auth
  /profiles
  /listings
    /ingestion
      adzuna_adapter.py
      graduates24_scraper.py
      normalize.py
  /matching
  /cv_tailoring
  /applications
  /skill_gap
  /monetization
    revenuecat_webhook.py
    gate.py              <- the single check_access() function
  /core
    config.py
    db.py
    models.py
main.py
```

---

## 8. Build order (sequence, not a calendar)

1. Auth + Profile (foundation everything else needs)
2. Listings ingestion — **Adzuna first** (fast, free, structured), scraping second (slower to get reliable)
3. Matching (depends on profiles + listings both existing)
4. CV tailoring (depends on matching for "why" reasoning, and on profile data)
5. Applications/tracking, including the email-apply send path
6. Skill-gap roadmap
7. RevenueCat integration — free-cap gate first (no ads, no payments — just cap → block), confirm the core features work end-to-end, **then** layer in ad-reward and premium purchase on top

Do not start on Section 5 (monetization) until Sections 3-6 (the actual product) work without it. A gating system around a feature that doesn't work yet is wasted effort.
