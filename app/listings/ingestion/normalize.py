from dataclasses import dataclass
from datetime import datetime

from app.core.models import ApplyMethod, ListingType
from app.listings.ingestion.skills import extract_required_skills


@dataclass(frozen=True)
class NormalizedListing:
    source: str
    source_listing_id: str
    title: str
    company: str | None
    location: str | None
    listing_type: ListingType
    salary_min: int | None
    salary_max: int | None
    description: str
    required_skills: list[str]
    apply_method: ApplyMethod
    apply_target: str
    posted_at: datetime | None


def classify_listing_type(title: str, description: str) -> ListingType:
    haystack = f"{title} {description}".lower()
    if "learnership" in haystack:
        return ListingType.learnership
    if "internship" in haystack or "intern " in haystack:
        return ListingType.internship
    if "apprentice" in haystack:
        return ListingType.apprenticeship
    if "bursary" in haystack:
        return ListingType.bursary
    return ListingType.job


def classify_apply_target(url: str | None, verified_contact_email: str | None = None) -> tuple[ApplyMethod, str]:
    """Decide how an application reaches the employer.

    ``verified_contact_email`` must come from a structured, source-provided
    field the ingestion adapter itself trusts (per-source verification is the
    adapter's job) — never from scanning free-text description content. A
    listing's description is untrusted, ingested text: regexing an email
    address out of it and then auto-emailing a candidate's CV there lets
    anyone who can influence that text (a scraped source, a compromised
    upstream feed) redirect real applications to an address of their choosing.
    Absent a verified contact email, every listing routes through the
    ``ats_link`` path, which never leaves the platform automatically — the
    user completes it themselves on the employer's own page.
    """
    if verified_contact_email:
        return ApplyMethod.email, verified_contact_email
    if url:
        return ApplyMethod.ats_link, url
    raise ValueError("Listing has no apply target")


def normalize_adzuna(raw: dict) -> NormalizedListing:
    title = raw.get("title") or "Untitled opportunity"
    description = raw.get("description") or ""
    # Adzuna's API exposes no structured, verified contact-email field — only
    # a redirect_url to the employer/ATS's own apply page — so every Adzuna
    # listing is classified ats_link. See classify_apply_target's docstring.
    apply_method, apply_target = classify_apply_target(raw.get("redirect_url"))
    company = (raw.get("company") or {}).get("display_name")
    location = (raw.get("location") or {}).get("display_name")
    posted_at = None
    if raw.get("created"):
        posted_at = datetime.fromisoformat(raw["created"].replace("Z", "+00:00"))

    return NormalizedListing(
        source="adzuna",
        source_listing_id=str(raw["id"]),
        title=title,
        company=company,
        location=location,
        listing_type=classify_listing_type(title, description),
        salary_min=_safe_int(raw.get("salary_min")),
        salary_max=_safe_int(raw.get("salary_max")),
        description=description,
        required_skills=extract_required_skills(f"{title} {description}"),
        apply_method=apply_method,
        apply_target=apply_target,
        posted_at=posted_at,
    )


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None

