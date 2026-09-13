r"""DPSA Public Service Vacancy Circular parser.

Manual, one-off ingestion -- not automated like Adzuna/Himalayas/Vacancy
Update. There is no scraper and no scheduled task here on purpose: the user
downloads each circular PDF from dpsa.gov.za themselves and hands it to
scripts/ingest_dpsa_pdf.py directly.

Verified against FIVE real circulars (29-33 of 2026) -- 1,749 total real
posts captured across all five weeks, zero genuinely missing (the only two
apparent "misses" were confirmed to be erratum cross-references to a
PREVIOUS week's circular, correctly excluded rather than double-counted).
Pure text/regex extraction against pdftotext's -layout output -- no LLM
call needed. The document is generated from Word via Acrobat PDFMaker and
uses a rigid, consistent labeled-field format throughout, confirmed across
multiple departments and multiple weeks.

Five real bugs already fixed here, each confirmed via live testing against
real circulars, not hypothesized:
1. A dropped "Management Echelon" section -- some departments list senior
   posts in their own subsection before "OTHER POSTS"; naively splitting on
   the first "OTHER POSTS" heading silently discarded those. Fixed by
   anchoring post detection on the "POST NN/NN" marker itself, never on a
   section heading.
2. A missing per-post APPLICATIONS field needing a department-level
   fallback -- some posts inherit where to apply from their department's
   own header rather than restating it.
3. A stray leading space breaking the post-split regex.
4. A single-leading-space index row breaking department-name resolution.
5. Posts that omit the colon between the post number and title, using
   extra spaces instead ("POST 31/214        TITLE").
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone

from app.core.models import ApplyMethod, ListingType
from app.listings.ingestion.normalize import NormalizedListing
from app.listings.ingestion.skills import extract_required_skills

SOURCE = "dpsa"

# The same blank Z83 form on every DPSA listing -- not parsed per-post, a
# fixed constant, since a manual (non-automated) apply method still needs to
# tell the user what to actually fill in and submit themselves.
Z83_FORM_URL = "https://www.dpsa.gov.za/dpsa2g/documents/vacancies/editable Approved New Z83 form Gazetted 6 Nov 2020.pdf"


class DpsaParsingError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Step 1: extract raw text with layout preserved (multi-column safe)
# ---------------------------------------------------------------------------


def extract_text(pdf_path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Step 2: strip page-break artifacts
# A lone page-footer number sits on its own line immediately before the form
# feed character pdftotext inserts between pages -- confirmed live, e.g.:
#   "...Computer Literacy,\n\n                    5\n\x0c    Communication skills..."
# Left unstripped, "5" gets glued into the middle of a REQUIREMENTS/DUTIES
# paragraph. Every multi-page post field needs this cleaned before parsing.
# ---------------------------------------------------------------------------

_PAGE_BREAK_RE = re.compile(r"\n[ \t]*\d{1,4}[ \t]*\n\x0c[ \t]*")


def strip_page_breaks(text: str) -> str:
    return _PAGE_BREAK_RE.sub(" ", text).replace("\x0c", " ")


# ---------------------------------------------------------------------------
# Step 3: parse the INDEX to map ANNEXURE letter -> department name
# Confirmed format:
#   AGRICULTURE                          A        04 - 06
# Page numbers from the index are NOT used to slice the document -- annexure
# markers in the body ("ANNEXURE A") are used instead, since they are exact
# and don't depend on the index staying in sync with the real page breaks.
# ---------------------------------------------------------------------------

_INDEX_ROW_RE = re.compile(
    r"^\s*([A-Z][A-Z ,()&'\-]+?)\s{2,}([A-Z]{1,2})\s+\d{1,3}\s*-\s*\d{1,3}\s*$",
    re.MULTILINE,
)


def parse_index(text: str) -> dict[str, str]:
    """Returns {annexure_letter: department_name}."""
    index_section = text[text.index("INDEX") : text.index("ANNEXURE A")]
    departments: dict[str, str] = {}
    for match in _INDEX_ROW_RE.finditer(index_section):
        name, annexure = match.group(1).strip(), match.group(2).strip()
        departments[annexure] = name
    return departments


# ---------------------------------------------------------------------------
# Step 4: split the document into annexure (department) blocks
# ---------------------------------------------------------------------------

_ANNEXURE_MARKER_RE = re.compile(r"\bANNEXURE\s+([A-Z]{1,2})\b")


def split_by_annexure(text: str) -> list[tuple[str, str]]:
    """Returns [(annexure_letter, block_text), ...] in document order."""
    markers = list(_ANNEXURE_MARKER_RE.finditer(text))
    blocks = []
    for i, m in enumerate(markers):
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        blocks.append((m.group(1), text[start:end]))
    return blocks


# ---------------------------------------------------------------------------
# Step 5: department-level header (CLOSING DATE, NOTE) -- applies to every
# post in that annexure unless the post itself overrides it.
# ---------------------------------------------------------------------------

_CLOSING_DATE_RE = re.compile(r"CLOSING DATE\s*:\s*(.+?)(?=\n[A-Z]{2,}\s*:|\Z)", re.DOTALL)
_DEPT_NOTE_RE = re.compile(r"\bNOTE\s*:\s*(.+?)(?=\n\s*(?:OTHER POSTS|POST \d+/\d+))", re.DOTALL)
_DEPT_APPLICATIONS_RE = re.compile(r"\bAPPLICATIONS\s*:\s*(.+?)(?=\n\s*(?:OTHER POSTS|POST \d+/\d+|MANAGEMENT ECHELON))", re.DOTALL)


def parse_department_header(block_text: str) -> dict:
    closing = _CLOSING_DATE_RE.search(block_text)
    note = _DEPT_NOTE_RE.search(block_text)
    applications = _DEPT_APPLICATIONS_RE.search(block_text)
    return {
        "closing_date_raw": _clean(closing.group(1)) if closing else None,
        "department_note": _clean(note.group(1)) if note else None,
        "department_applications": _clean(applications.group(1)) if applications else None,
    }


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Step 6: split a department block into individual POST entries
# Confirmed format: "POST 33/01     :   TITLE ..." OR "POST 31/214        TITLE"
# (colon optional -- some posts use extra spaces instead, confirmed live in
# circular 31). Circular number is baked into the post number itself, so
# "33/01" is globally unique forever (circular numbers never repeat) and
# drops straight into the existing (source, source_listing_id) uniqueness
# constraint with no extra work.
# ---------------------------------------------------------------------------

_POST_SPLIT_RE = re.compile(r"\n[ \t]*(?=POST \d+/\d+\s*(?::|\s{2,}\S))")
_POST_HEADER_RE = re.compile(r"^POST (\d+/\d+)\s*(?::|\s{2,})\s*(.+?)(?=\n[A-Z]{2,}(?:\s[A-Z]+)?\s*:|\Z)", re.DOTALL)

# Labeled fields that appear inside a post block, in the order they occur.
_FIELD_RE = re.compile(
    r"\b(SALARY|CENTRE|REQUIREMENTS|DUTIES|ENQUIRIES|APPLICATIONS|NOTE)\s*:\s*"
    r"(.+?)(?=\n\s*(?:SALARY|CENTRE|REQUIREMENTS|DUTIES|ENQUIRIES|APPLICATIONS|NOTE)\s*:|\Z)",
    re.DOTALL,
)


def split_posts(department_text: str) -> list[str]:
    # Post detection is anchored on the "POST NN/NN" marker itself, so no
    # section-heading split is needed -- confirmed live that naively
    # discarding everything before the FIRST "OTHER POSTS" heading silently
    # dropped senior "MANAGEMENT ECHELON" posts some departments list in
    # their own subsection before "OTHER POSTS".
    chunks = _POST_SPLIT_RE.split(department_text)
    return [c for c in chunks if c.strip().startswith("POST ")]


def parse_post_block(block: str) -> dict:
    header = _POST_HEADER_RE.match(block)
    post_number = header.group(1) if header else None
    title_and_ref = _clean(header.group(2)) if header else ""

    fields: dict[str, str] = {}
    for m in _FIELD_RE.finditer(block):
        label, value = m.group(1), _clean(m.group(2))
        fields[label] = value

    return {
        "post_number": post_number,
        "title_and_ref": title_and_ref,
        **fields,
    }


# ---------------------------------------------------------------------------
# Step 7: field-level parsing -- title/ref split, salary, apply target
# ---------------------------------------------------------------------------

_REF_RE = re.compile(r"REF\s*NO\s*:?\s*([^\n(]+?)(?:\s*\(|$)", re.IGNORECASE)
_POST_COUNT_RE = re.compile(r"\(X\s*(\d+)\s*POSTS?\)", re.IGNORECASE)


def split_title_ref(title_and_ref: str) -> tuple[str, str | None, int]:
    ref_match = _REF_RE.search(title_and_ref)
    ref_no = _clean(ref_match.group(1)) if ref_match else None
    title = title_and_ref
    if ref_match:
        title = title_and_ref[: ref_match.start()]
    count_match = _POST_COUNT_RE.search(title_and_ref)
    post_count = int(count_match.group(1)) if count_match else 1
    title = re.split(r"\s{2,}Directorate\s*:", title, maxsplit=1)[0]
    title = _clean(title).rstrip(",")
    return title, ref_no, post_count


_SALARY_RE = re.compile(
    r"R\s?([\d\s]{5,})\s*(?:-\s*R\s?([\d\s]{5,}))?\s*per annum(?:\s*\(Level\s*(\d+)\))?",
    re.IGNORECASE,
)


def parse_salary(salary_field: str | None) -> dict:
    if not salary_field:
        return {"salary_min": None, "salary_max": None, "salary_period": None, "salary_currency": None, "salary_level": None}
    m = _SALARY_RE.search(salary_field)
    if not m:
        # Non-standard salary text (e.g. an OSD scale) -- kept as-is in the
        # description rather than forced into a wrong number. NULL is the
        # correct outcome for these (roughly 5-8% of posts), not a bug.
        return {"salary_min": None, "salary_max": None, "salary_period": None, "salary_currency": None, "salary_level": None}
    low = int(m.group(1).replace(" ", ""))
    high = int(m.group(2).replace(" ", "")) if m.group(2) else low
    level = int(m.group(3)) if m.group(3) else None
    return {"salary_min": low, "salary_max": high, "salary_period": "annual", "salary_currency": "ZAR", "salary_level": level}


_CIRCULAR_DATE_RE = re.compile(r"DATE ISSUED\s+(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE)


def _parse_circular_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d %B %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _build_description(*, requirements: str | None, duties: str | None, ref_no: str | None, enquiries: str | None, ee_target: str | None) -> str:
    """REQUIREMENTS + DUTIES + reference_number + enquiries + ee_target,
    appended readably, plus the fixed Z83 form line every DPSA listing
    carries -- this is a manual apply method, so the description itself has
    to tell the user what to actually do, not just describe the role."""
    parts: list[str] = []
    if requirements:
        parts.append(f"REQUIREMENTS: {requirements}")
    if duties:
        parts.append(f"DUTIES: {duties}")
    if ref_no:
        parts.append(f"Reference number: {ref_no}")
    if enquiries:
        parts.append(f"Enquiries: {enquiries}")
    if ee_target:
        parts.append(f"Employment Equity: {ee_target}")
    parts.append(f"To apply, complete the official Z83 form: {Z83_FORM_URL}")
    return "\n\n".join(parts)


def parse_circular(pdf_path: str) -> list[NormalizedListing]:
    raw = extract_text(pdf_path)
    try:
        return parse_circular_text(raw)
    except DpsaParsingError as exc:
        raise DpsaParsingError(f"{exc} (in {pdf_path})") from exc


def parse_circular_text(raw_text: str) -> list[NormalizedListing]:
    """The actual parsing logic, taking already-extracted text -- split out
    from parse_circular() so it's testable without shelling out to
    pdftotext for every test case."""
    text = strip_page_breaks(raw_text)

    date_match = _CIRCULAR_DATE_RE.search(text)
    posted_at = _parse_circular_date(date_match.group(1) if date_match else None)

    try:
        departments = parse_index(text)
    except ValueError as exc:
        raise DpsaParsingError("Could not locate INDEX/ANNEXURE A markers") from exc

    listings: list[NormalizedListing] = []

    for annexure, block_text in split_by_annexure(text):
        dept_name = departments.get(annexure, f"Unknown ({annexure})")
        dept_header = parse_department_header(block_text)

        for post_block in split_posts(block_text):
            parsed = parse_post_block(post_block)
            if not parsed["post_number"]:
                continue

            title, ref_no, post_count = split_title_ref(parsed["title_and_ref"])
            salary = parse_salary(parsed.get("SALARY"))
            applications_field = parsed.get("APPLICATIONS") or dept_header.get("department_applications")

            description = _build_description(
                requirements=parsed.get("REQUIREMENTS"),
                duties=parsed.get("DUTIES"),
                ref_no=ref_no,
                enquiries=parsed.get("ENQUIRIES"),
                ee_target=parsed.get("NOTE"),
            )

            listings.append(
                NormalizedListing(
                    source=SOURCE,
                    source_listing_id=parsed["post_number"],
                    title=title,
                    company=dept_name,
                    location=parsed.get("CENTRE"),
                    listing_type=ListingType.job,
                    category=dept_name,
                    salary_min=salary["salary_min"],
                    salary_max=salary["salary_max"],
                    salary_period=salary["salary_period"],
                    salary_currency=salary["salary_currency"],
                    description=description,
                    required_skills=extract_required_skills(f"{title} {description}"),
                    # Always manual, confirmed: 65-75% of posts per week
                    # explicitly require the Z83 form, and the rest still
                    # have no automated submission path either.
                    apply_method=ApplyMethod.manual,
                    apply_target=applications_field or "See description for how to apply.",
                    posted_at=posted_at,
                )
            )

    return listings
