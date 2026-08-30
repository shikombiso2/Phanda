You are building the backend for **Phanda**, a mobile employment app for South African youth (Android, Google Play Store). Follow the attached architecture document exactly — do not introduce new services, patterns, or dependencies that aren't specified in it.

## Stack
- Python + FastAPI
- PostgreSQL
- Celery + Redis for background/scheduled jobs
- S3-compatible storage for generated CV/cover letter files
- JWT auth, phone number + OTP as the primary login method
- Anthropic API (Claude) for CV/cover letter generation
- SendGrid or Mailgun for transactional email (used to send applications for email-apply listings)
- RevenueCat webhook integration for monetization state (do NOT build custom AdMob ad-verification logic — RevenueCat handles that; you only need to build the webhook receiver and the local gate logic described below)

## Build in this order — do not skip ahead
1. **Auth** — phone + OTP request/verify, JWT issuance
2. **Profiles** — CRUD matching the fields in the architecture doc (job type, location, remote toggle, skills, industries, education level, experience level, salary range, CV upload)
3. **Listings ingestion** — build the Adzuna API adapter FIRST (it's free, structured, and fast to integrate — register for a free App ID/App Key at the Adzuna developer portal, country=za). Build the normalization layer so Adzuna and any future scraper source write into the exact same `listings` schema. Do not build scraper modules until the Adzuna adapter and normalization layer are working end-to-end.
4. **Matching** — simple, explainable keyword/tag overlap between profile skills and listing required_skills. Do not build an ML ranking model. The score must come with a "why" breakdown (which skills matched, which are missing) — this is a core product requirement, not optional.
5. **CV tailoring** — calls the Anthropic API with the user's profile + a specific listing to generate a tailored CV and cover letter. Every call MUST pass through the gate function (see Monetization section) before calling the LLM. Store outputs in S3, link to the relevant application record.
6. **Applications/tracking** — for listings where apply_method is "email", send the tailored application via SendGrid/Mailgun from our domain. For "ats_link" listings, do not attempt automated submission — return the tailored files plus the direct listing URL for the user to complete manually. Record an application row either way.
7. **Skill-gap roadmap** — free tier shows the flagged skill gap only. The full roadmap (ordered resources/courses) is gated behind the same access-check function used for CV tailoring, using a lookup table (skill → 2-3 resource links), not a generative or ML approach.
8. **Monetization** — build this LAST, after 1-7 work end-to-end without it. Build:
   - The `feature_usage`, `entitlements`, and `wallet` tables exactly as specified in the architecture doc
   - **One single function**, `check_access(user_id, feature_key)`, implementing the four-step gate logic in Section 5.5 of the architecture doc. Both CV tailoring and skill-gap roadmap must call this same function — do not write separate gating logic for each feature.
   - **One single webhook endpoint** at `/webhooks/revenuecat` that handles purchase events (updating `entitlements`) and virtual currency events (updating `wallet`). Verify the webhook signature before trusting any payload.
   - Do NOT build any AdMob server-side-verification logic yourself. RevenueCat handles ad verification and reward granting via dashboard configuration — your only job on the ads side is to reflect the resulting webhook events into the local `wallet` table, and to enforce the "once per day" ad-offer cap yourself using `feature_usage.ad_reward_date`.

## Hard constraints
- Every listing must have a normalized `apply_method` of either `"ats_link"` or `"email"` — this determines the entire apply flow downstream, so ingestion must classify it correctly at write time, not leave it for later.
- Never store binary files (CVs, generated documents) in Postgres — S3 only, store the path/URL.
- The matching score must always be explainable (return which specific skills matched/were missing), never a bare number.
- Respect robots.txt and reasonable request rates on any future scraper — do not build anything that scrapes LinkedIn.
- All monetization gating happens server-side. Never trust a client-reported "ad watched" or "purchase completed" event — only RevenueCat webhook events and your own database state are the source of truth.

## What NOT to build in this pass
- No ML-based matching or ranking
- No custom ad-verification/SSV endpoint
- No PayFast/Yoco integration — this is a native Android app, payments go through Google Play Billing via RevenueCat only
- No separate premium entitlement per feature — one combined `phanda_premium` entitlement covers both CV tailoring and skill-gap roadmap for MVP
- No automated form-filling/submission for ats_link listings

Refer to the attached architecture document for full data models, the complete API surface, and the exact gate-logic pseudocode. If anything in this prompt and the architecture document conflicts, the architecture document is authoritative.
