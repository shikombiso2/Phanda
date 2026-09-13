r"""vacancyupdate.co.za parser, ported from phanda-scrapers/vacancyupdate_parser.py
(11/15 fully extracted on the confirmed live sample) into this codebase's
NormalizedListing shape.

Discovery reads the site's sitemap.xml rather than crawling category pages,
same rationale as Himalayas: the sitemap's `lastmod` is not the job's closing
date (a post sits unmodified for months after its deadline passes), so it is
used only to bound *which posts to fetch*, never as the expiry itself --
that comes from each post's own "Closing Date" text.

Deliberately httpx.AsyncClient with bounded per-request retries and a polite
delay between post fetches, the same shape as AdzunaClient/HimalayasClient --
not `requests`, even though that's already a dependency elsewhere in this
codebase (app/auth/google.py), so every ingestion source shares one retry/
backoff convention rather than three.

Three structural bugs fixed here versus the original script, each confirmed
against real fetched pages (see phanda-scrapers/scrape_output.txt):

1. Company name captured "the X" instead of "X" when the site's own "About"
   heading reads "About the Clicks" rather than "About Clicks" (real example:
   the Clicks Youth Employment Programme post).
2. Location capture bled across lines -- "Sandton\n, this full" and
   "Gauteng\nIndustry" were both really captured on live pages, because the
   original character class `[\w\s,]+` treats `\s` as matching newlines too.
   Fixed by capturing up to the first newline only.
3. Closing dates given as an inline "Closing Date: <date>" label (no "on",
   not its own section -- real example: the Clicks post's "(Closing Date:
   09 September 2026)" inside the Application Process paragraph) were missed
   entirely by the original "closing date ... on <date>" phrasing. Both
   phrasings are matched now. Separately, a captured date can still contain
   an internal newline ("14 September\n2026" -- confirmed real, e.g. the
   Metropolitan post) since the regex's own \s already spans lines; that is
   handled by whitespace-normalizing before parsing, not a regex change.

A fourth, unlisted issue also showed up in the same live sample and is fixed
here too rather than left in: the original script only looked for an
"Application Instructions" heading before the real apply link. Real posts
use at least four different headings for the same thing ("Application
Instructions", "Application Process", "Application Procedure", "How to
Apply"), and one (Clicks) uses no heading at all. Every single one of the 15
sampled posts does contain the literal phrase "Apply online" immediately
before the real link, so that phrase -- not a heading -- is the anchor point
used to find the apply target. This directly fixed 3 of the 4 originally
"unconfirmed" posts in the live sample (Givaudan, Experian, Clicks); see the
worker-run report for the actual outcome.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import httpx
from defusedxml import ElementTree as ET

from app.core.models import ApplyMethod
from app.core.observability import emit_event
from app.listings.ingestion.normalize import NormalizedListing, classify_listing_type
from app.listings.ingestion.skills import extract_required_skills

SOURCE = "vacancyupdate"
BASE_URL = "https://vacancyupdate.co.za"
DEFAULT_BACKFILL_SINCE = datetime(2026, 8, 1, tzinfo=timezone.utc)
ONGOING_LOOKBACK_DAYS = 8
"""A little more than the 7-day gap between twice-weekly runs, so a post
whose sitemap lastmod lands right before a delayed run doesn't slip through."""

_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PhandaBot/1.0; +https://phanda.example)"}
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES_PER_REQUEST = 2
_RETRY_BACKOFF_SECONDS = 1.5
_PAUSE_BETWEEN_POSTS_SECONDS = 1.0
"""Polite delay between per-post fetches -- this is a free, ad-supported
site hit on a schedule, not a paid API with a quota to spend efficiently."""

_EXCLUDED_URL_SEGMENTS = ("/vacancies/", "/author/", "/about", "/privacy", "/dmca", "/disclaimer", "/contact", "/wp-")


class VacancyUpdateFetchError(RuntimeError):
    """A post or sitemap fetch failed after retries -- transient (network,
    5xx, 429) rather than a structural parsing problem."""


@dataclass(frozen=True)
class _SitemapEntry:
    url: str
    lastmod: datetime | None


def _parse_sitemap_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_post_url(url: str) -> bool:
    if url.rstrip("/") == BASE_URL:
        return False
    return not any(segment in url for segment in _EXCLUDED_URL_SEGMENTS)


class VacancyUpdateClient:
    """Same shape as AdzunaClient/HimalayasClient: fetch with bounded
    retries, discover via one entry point, fetch_all orchestrates."""

    def __init__(self) -> None:
        pass

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, *, context: str) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES_PER_REQUEST + 1):
            try:
                response = await client.get(url, headers=_REQUEST_HEADERS, timeout=20)
                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES_PER_REQUEST:
                    emit_event("vacancyupdate_retry", context=context, http_status=response.status_code, attempt=attempt + 1)
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                # httpx surfaces the transient SSL drops observed live
                # against this site as ConnectError/TransportError, not a
                # distinct SSL-specific exception -- caught here generically.
                last_exc = exc
                if attempt < _MAX_RETRIES_PER_REQUEST:
                    emit_event("vacancyupdate_retry", context=context, reason="network_error", attempt=attempt + 1)
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
            except httpx.HTTPStatusError as exc:
                raise VacancyUpdateFetchError(f"{context}: {exc}") from exc
        raise VacancyUpdateFetchError(f"{context}: exhausted retries") from last_exc

    async def discover_urls(self, client: httpx.AsyncClient, *, since: datetime) -> list[_SitemapEntry]:
        """Reads sitemap.xml, following a Yoast-style sitemap INDEX into its
        post-sitemap* sub-sitemaps if present, and returns only post URLs
        with lastmod >= since. Non-post sitemaps (pages, authors, categories)
        and non-post URL segments are excluded."""
        response = await self._get_with_retry(client, f"{BASE_URL}/sitemap.xml", context="sitemap_index")
        root = ET.fromstring(response.content)

        sub_sitemaps = [loc.text for loc in root.findall(f"{_SITEMAP_NS}sitemap/{_SITEMAP_NS}loc") if loc.text]
        entries: list[_SitemapEntry] = []

        if sub_sitemaps:
            emit_event("vacancyupdate_sitemap_index", sub_sitemap_count=len(sub_sitemaps))
            for sitemap_url in sub_sitemaps:
                if "post-sitemap" not in sitemap_url:
                    continue
                sub_response = await self._get_with_retry(client, sitemap_url, context="post_sitemap")
                sub_root = ET.fromstring(sub_response.content)
                for url_tag in sub_root.findall(f"{_SITEMAP_NS}url"):
                    loc = url_tag.find(f"{_SITEMAP_NS}loc")
                    lastmod = url_tag.find(f"{_SITEMAP_NS}lastmod")
                    if loc is not None and loc.text:
                        entries.append(_SitemapEntry(url=loc.text, lastmod=_parse_sitemap_datetime(lastmod.text if lastmod is not None else None)))
                await asyncio.sleep(0.5)
        else:
            for url_tag in root.findall(f"{_SITEMAP_NS}url"):
                loc = url_tag.find(f"{_SITEMAP_NS}loc")
                lastmod = url_tag.find(f"{_SITEMAP_NS}lastmod")
                if loc is not None and loc.text:
                    entries.append(_SitemapEntry(url=loc.text, lastmod=_parse_sitemap_datetime(lastmod.text if lastmod is not None else None)))

        filtered = [e for e in entries if _is_post_url(e.url) and e.lastmod is not None and e.lastmod >= since]
        emit_event("vacancyupdate_discovered", total_sitemap_entries=len(entries), matching_since_cutoff=len(filtered))
        return filtered

    async def fetch_all(self, *, since: datetime) -> list[NormalizedListing]:
        rows: list[NormalizedListing] = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            entries = await self.discover_urls(client, since=since)
            for i, entry in enumerate(entries):
                try:
                    response = await self._get_with_retry(client, entry.url, context="post")
                except VacancyUpdateFetchError:
                    emit_event("vacancyupdate_post_failed", url=entry.url, reason="fetch_error")
                    continue
                try:
                    row = parse_post(entry.url, response.text)
                except ValueError as exc:
                    emit_event("vacancyupdate_post_skipped", url=entry.url, reason=str(exc))
                    continue
                rows.append(row)
                if i < len(entries) - 1:
                    await asyncio.sleep(_PAUSE_BETWEEN_POSTS_SECONDS)
        emit_event("vacancyupdate_fetched", listing_count=len(rows))
        return rows


# ---------------------------------------------------------------------------
# Post parsing
# ---------------------------------------------------------------------------

_BLOCK_LEVEL_JOIN = "\n"


_CONTENT_CLASS_RE = re.compile(r"entry-content|post-content|content-area", re.IGNORECASE)


class _ContentExtractor(HTMLParser):
    """Flattens a page to plain text the same way BeautifulSoup's
    `.get_text("\\n", strip=True)` does -- one line per text node in document
    order, blank/whitespace-only nodes dropped -- since the confirmed regex
    patterns below were tuned against exactly that shape of text. Also
    records the first <h1> text and every off-site anchor's href alongside
    the text-node index it appeared at, so the apply link can be found
    relative to a text marker without needing a DOM (no bs4 dependency).

    Text nodes are collected only from inside the post's own content div
    (matched the same way the original bs4 script found it: a div classed
    entry-content/post-content/content-area). This was NOT optional --
    live testing showed the site's sidebar/related-posts widgets contain
    incidental occurrences of "Centre" and "based in" that, without this
    scoping, got captured as the post's own location. <h1> is read
    regardless of the content div, since the page title lives outside it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.strings: list[str] = []
        self.h1: str | None = None
        self._in_h1 = False
        self.anchors: list[tuple[int, str]] = []
        self._pending_href: str | None = None
        self._content_div_depth: int | None = None  # None = not yet inside; 0+ = nested <div> depth inside it

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        if tag == "h1" and self.h1 is None:
            self._in_h1 = True
        if self._content_div_depth is None:
            if tag == "div" and _CONTENT_CLASS_RE.search(attrs_dict.get("class", "")):
                self._content_div_depth = 0
            return
        if tag == "div":
            self._content_div_depth += 1
        if tag == "a" and attrs_dict.get("href"):
            self._pending_href = attrs_dict["href"]

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_h1 = False
        if self._content_div_depth is None:
            return
        if tag == "div":
            if self._content_div_depth == 0:
                self._content_div_depth = None  # left the content div entirely
            else:
                self._content_div_depth -= 1
        if tag == "a":
            self._pending_href = None

    def handle_data(self, data: str) -> None:
        if self._in_h1 and self.h1 is None:
            self.h1 = data.strip() or None
        if self._content_div_depth is None:
            return
        stripped = data.strip()
        if not stripped:
            return
        if self._pending_href:
            self.anchors.append((len(self.strings), self._pending_href))
        self.strings.append(stripped)

    def text(self) -> str:
        return _BLOCK_LEVEL_JOIN.join(self.strings)


_COMPANY_RE = re.compile(r"About\s+(?:the\s+)?(.+)", re.IGNORECASE)
# Two shapes, both confirmed real: "Location: Gauteng" as one paragraph
# (inline value after the colon), or a label alone at the end of its own
# line/sentence ("...available in this location:", "Based in") with the
# value entirely on the NEXT text node. Either way the label must reach the
# end of its own text node -- NOT true mid-sentence prose that merely
# contains "based in" as a substring (confirmed real: "classroom-based
# instruction" on the Clicks post matched the old unanchored version).
_LOCATION_INLINE_RE = re.compile(r"(?:Location|Centre|Based in)\s*:\s*(.+)$", re.IGNORECASE)
_LOCATION_LABEL_ONLY_RE = re.compile(r"(?:Location|Centre|Based in)\s*:?\s*$", re.IGNORECASE)
_INDUSTRY_INLINE_RE = re.compile(r"Industry\s*:\s*(.+)$", re.IGNORECASE)
_INDUSTRY_LABEL_ONLY_RE = re.compile(r"Industry\s*:?\s*$", re.IGNORECASE)
_APPLY_ONLINE_RE = re.compile(r"apply online", re.IGNORECASE)
_CF_EMAIL_RE = re.compile(r'data-cfemail="([a-f0-9]+)"')

# Two real phrasings, both confirmed on live pages: a sentence ("...before
# the closing date on <date>") and a bare label ("Closing Date: <date>",
# which can appear inline in a paragraph with no "on" and no section of its
# own -- see the Clicks post).
_CLOSING_DATE_RE = re.compile(
    r"closing date[^.]{0,120}?\bon\s+\*{0,2}(\d{1,2}\s+\w+\s+\d{4})\*{0,2}"
    r"|closing date\s*:\s*\*{0,2}(\d{1,2}\s+\w+\s+\d{4})\*{0,2}",
    re.IGNORECASE,
)


def decode_cf_email(encoded: str) -> str | None:
    """Standard, well-known decode for Cloudflare's email-protection
    obfuscation -- confirmed necessary against a real post that gives only
    an email, no link."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i : i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except (ValueError, IndexError):
        return None


def _parse_closing_date(full_text: str) -> datetime | None:
    match = _CLOSING_DATE_RE.search(full_text)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    # A date can carry an internal newline ("14 September\n2026", confirmed
    # real) since \s in the pattern above already spans lines -- normalize
    # before parsing rather than widen the regex further.
    normalized = " ".join(raw.split())
    try:
        return datetime.strptime(normalized, "%d %B %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _extract_labeled_value(strings: list[str], inline_re: re.Pattern, label_only_re: re.Pattern) -> str | None:
    """Finds a "Label: value" or "Label:" (value on the next text node)
    occurrence. Rejects any text node where the label appears mid-sentence
    with more content following it on the SAME node (confirmed real false
    positive: "...classroom-based instruction with hands-on training..."),
    since neither pattern matches unless the label reaches the end of that
    node."""
    for i, s in enumerate(strings):
        inline_match = inline_re.search(s)
        if inline_match:
            value = inline_match.group(1).strip()
            if value:
                return value
            continue
        if label_only_re.search(s) and i + 1 < len(strings):
            candidate = strings[i + 1].strip()
            if candidate:
                return candidate
    return None


def _find_apply_target(full_text: str, strings: list[str], anchors: list[tuple[int, str]]) -> tuple[str, str] | None:
    """Every one of the 15 live-sampled posts contains the literal phrase
    "Apply online" immediately before the real link -- a far more reliable
    anchor than a heading, since real posts use at least four different
    heading phrasings for the same thing ("Application Instructions",
    "Application Process", "Application Procedure", "How to Apply") and one
    (Clicks) uses none at all. Finds the first off-site anchor at or after
    the text node containing "Apply online"."""
    marker_index: int | None = None
    for i, s in enumerate(strings):
        if _APPLY_ONLINE_RE.search(s):
            marker_index = i
            break
    if marker_index is None:
        return None
    for anchor_index, href in anchors:
        if anchor_index < marker_index:
            continue
        if href.startswith("http") and "vacancyupdate.co.za" not in href:
            return "link", href
    return None


def parse_post(url: str, html: str) -> NormalizedListing:
    """Raises ValueError (caught by the caller, which skips the post) when
    no apply target can be found at all -- apply_target is a required field
    on Listing, so a post with genuinely neither a real link nor a decodable
    email cannot be stored, the same rule Himalayas' adapter follows."""
    extractor = _ContentExtractor()
    extractor.feed(html)
    extractor.close()

    title = extractor.h1 or "Untitled opportunity"
    full_text = extractor.text()

    company_match = _COMPANY_RE.search(full_text)
    company = company_match.group(1).strip() if company_match else None

    location = _extract_labeled_value(extractor.strings, _LOCATION_INLINE_RE, _LOCATION_LABEL_ONLY_RE)
    location = location[:255] if location else None

    category = _extract_labeled_value(extractor.strings, _INDUSTRY_INLINE_RE, _INDUSTRY_LABEL_ONLY_RE)
    category = category[:120] if category else None

    apply_result = _find_apply_target(full_text, extractor.strings, extractor.anchors)
    if apply_result:
        apply_method, apply_target = "link", apply_result[1]
    else:
        cf_match = _CF_EMAIL_RE.search(html)
        decoded = decode_cf_email(cf_match.group(1)) if cf_match else None
        if not decoded:
            raise ValueError("no_apply_target")
        apply_method, apply_target = "email", decoded

    slug = url.rstrip("/").rsplit("/", 1)[-1]

    return NormalizedListing(
        source=SOURCE,
        source_listing_id=slug,
        title=title,
        company=company,
        location=location,
        listing_type=classify_listing_type(title, full_text),
        category=category,
        salary_min=None,
        salary_max=None,
        description=full_text,
        required_skills=extract_required_skills(f"{title} {full_text}"),
        apply_method=_APPLY_METHOD_MAP[apply_method],
        apply_target=apply_target,
        posted_at=None,
        expires_at=_parse_closing_date(full_text),
    )

_APPLY_METHOD_MAP = {"link": ApplyMethod.ats_link, "email": ApplyMethod.email}
