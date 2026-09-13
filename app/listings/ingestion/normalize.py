from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser

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
    category: str | None
    salary_min: int | None
    salary_max: int | None
    description: str
    required_skills: list[str]
    apply_method: ApplyMethod
    apply_target: str
    posted_at: datetime | None
    salary_period: str | None = "annual"
    salary_currency: str | None = "ZAR"
    """Units for salary_min/salary_max. The defaults describe Adzuna ZA --
    the only source that existed when these columns were added, and the same
    values its existing rows were backfilled to -- so an adapter that quotes
    annual ZAR needs to say nothing. Any source quoting anything else must
    pass its own values explicitly."""
    expires_at: datetime | None = None
    """Source-stated end of the posting. None means the source publishes no
    expiry and the listing relies on last_seen_at staleness alone."""


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
    category = (raw.get("category") or {}).get("label")
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
        category=category,
        salary_min=_safe_int(raw.get("salary_min")),
        salary_max=_safe_int(raw.get("salary_max")),
        description=description,
        required_skills=extract_required_skills(f"{title} {description}"),
        apply_method=apply_method,
        apply_target=apply_target,
        posted_at=posted_at,
    )


_BLOCK_TAGS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "tr", "section", "article", "blockquote"}


class _HtmlTextExtractor(HTMLParser):
    """Flattens HTML to plain text, keeping paragraph and list structure.

    Sources that return HTML descriptions cannot have that HTML stored: the
    text is fed to the CV-tailoring model as candidate context, where tags
    are noise at best and instructions at worst. convert_charrefs (on by
    default) also resolves &amp;/&#39; and friends, which a regex strip would
    leave behind.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "li":
            self._parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS or tag == "li":
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        joined = "".join(self._parts)
        # Collapse runs of blank lines the tag boundaries above introduce,
        # and trim trailing spaces, without touching single line breaks --
        # those are the paragraph and list structure worth preserving.
        lines = [line.strip() for line in joined.splitlines()]
        out: list[str] = []
        for line in lines:
            if line or (out and out[-1]):
                out.append(line)
        return "\n".join(out).strip()


def html_to_text(html: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def normalize_himalayas(raw: dict) -> NormalizedListing:
    """Map one Himalayas browse-API job onto NormalizedListing.

    Attribution: Himalayas' terms require linking back to the job on their
    site and crediting them as the source. Both `guid` and `applicationLink`
    are himalayas.app job URLs (verified identical across sampled live
    responses), so apply_target already carries the link their terms require
    and source="himalayas" carries the credit. Note the consequence: this is
    the Himalayas listing page, NOT the employer's own ATS -- the API exposes
    no direct employer URL at all.
    """
    title = raw.get("title") or "Untitled opportunity"
    description = html_to_text(raw.get("description") or "")
    apply_target = raw.get("applicationLink") or raw.get("guid")
    if not apply_target:
        raise ValueError("Himalayas listing has no apply target")

    categories = raw.get("parentCategories") or raw.get("categories") or []
    restrictions = raw.get("locationRestrictions") or []

    return NormalizedListing(
        source="himalayas",
        source_listing_id=str(raw["guid"]),
        title=title,
        company=raw.get("companyName"),
        # Every Himalayas listing is remote by definition; locationRestrictions
        # narrows *where* you may be remote from. An empty list means no
        # restriction at all, i.e. worldwide.
        location=_remote_location(restrictions),
        listing_type=classify_listing_type(title, description),
        category=categories[0] if categories else None,
        salary_min=_safe_int(raw.get("minSalary")),
        salary_max=_safe_int(raw.get("maxSalary")),
        # Stored exactly as reported, no conversion: these are frequently USD
        # or CAD, and frequently hourly rather than annual.
        salary_period=raw.get("salaryPeriod"),
        salary_currency=raw.get("currency"),
        description=description,
        required_skills=extract_required_skills(f"{title} {description}"),
        apply_method=ApplyMethod.ats_link,
        apply_target=apply_target,
        posted_at=_epoch_to_datetime(raw.get("pubDate")),
        expires_at=_epoch_to_datetime(raw.get("expiryDate")),
    )


def _remote_location(restrictions: list[str]) -> str:
    if not restrictions:
        return "Remote (Worldwide)"
    label = f"Remote ({', '.join(str(item) for item in restrictions)})"
    # listings.location is String(255); a listing open to dozens of countries
    # would otherwise overflow it on insert.
    return label if len(label) <= 255 else label[:252] + "..."


def _epoch_to_datetime(value: object) -> datetime | None:
    """Himalayas returns pubDate/expiryDate as Unix epoch seconds, not the
    ISO-8601 strings Adzuna uses."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None

