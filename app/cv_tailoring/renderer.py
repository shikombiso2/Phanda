"""Render a validated TailoredCv to PDF.

Jinja2 + WeasyPrint rather than hand-placed ReportLab flowables: the output
is a CV a hiring manager reads, so it needs real typographic hierarchy
(name > section > role > bullet) and real bullet glyphs, and expressing that
as HTML/CSS is both far less code and far easier to adjust than stacking
styled Paragraph objects. The previous implementation had exactly two styles
for the whole document -- 14pt bold headers and 10pt body for everything
else, including the candidate's own name -- and no bullets at all.

This module only decides how already-generated, already-validated content is
laid out. It never changes, reorders or reinterprets what the pipeline
produced: TailoredCv's schema, generation and validation are untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.cv_tailoring.schemas import TailoredCv

_TEMPLATE_DIR = Path(__file__).parent / "templates"

# autoescape is not optional here: every string in a TailoredCv came back
# from a language model, and an unescaped "&" or "<" in a claim would
# otherwise corrupt the markup or silently swallow text.
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(default_for_string=True, default=True),
    trim_blocks=True,
    lstrip_blocks=True,
)

# Section names come from the model, so match on intent rather than an exact
# string -- real drafts have used both "Personal Details" and "Contact
# Information", both "Work Experience" and "Professional Experience".
_CONTACT_SECTION_RE = re.compile(r"contact|personal\s+(?:details|information)", re.IGNORECASE)
_PROSE_SECTION_RE = re.compile(r"summary|profile|objective", re.IGNORECASE)

_PARENTHETICAL_RE = re.compile(r"\(([^)]*)\)")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_RANGE_RE = re.compile(r"[-–—]|\bto\b", re.IGNORECASE)
_PRESENT_RE = re.compile(r"\b(?:present|current|ongoing)\b", re.IGNORECASE)


@dataclass
class _Entry:
    """One role: its heading line, its dates, and the achievements under it."""

    heading: str | None = None
    dates: str | None = None
    bullets: list[str] = field(default_factory=list)


@dataclass
class _Section:
    name: str
    layout: str  # "prose" | "entries" | "list"
    paragraphs: list[str] = field(default_factory=list)
    entries: list[_Entry] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


def _is_date_parenthetical(inner: str) -> bool:
    """True for "(Feb 2023 - Dec 2023)" or "(Jan 2024 - Present)", false for
    "(Internship)", "(Matric)" or a bare "(2022)".

    A lone year is deliberately not enough: an education line ends in one
    ("...Johannesburg (2022)") and must stay a bullet rather than being
    promoted to a role heading.
    """
    if _PRESENT_RE.search(inner):
        return True
    return bool(_YEAR_RE.search(inner) and _RANGE_RE.search(inner))


def _split_role_and_dates(text: str) -> tuple[str, str | None]:
    """Peel a trailing date range off a role line so it can be set in muted
    secondary type. Returns the line unchanged when there's nothing to peel."""
    matches = [m for m in _PARENTHETICAL_RE.finditer(text) if _is_date_parenthetical(m.group(1))]
    if not matches:
        return text, None
    last = matches[-1]
    heading = (text[: last.start()] + text[last.end() :]).strip(" ,-–—")
    return heading or text, last.group(1).strip()


def _looks_like_role_heading(text: str) -> bool:
    return any(_is_date_parenthetical(m.group(1)) for m in _PARENTHETICAL_RE.finditer(text))


def _group_into_entries(claims: list[str]) -> list[_Entry]:
    """A claim carrying a date range opens a new role; everything after it is
    that role's achievements, until the next one. Claims appearing before any
    role heading keep their place in a headless leading entry rather than
    being dropped."""
    entries: list[_Entry] = []
    current: _Entry | None = None
    for text in claims:
        if _looks_like_role_heading(text):
            heading, dates = _split_role_and_dates(text)
            current = _Entry(heading=heading, dates=dates)
            entries.append(current)
            continue
        if current is None:
            current = _Entry()
            entries.append(current)
        current.bullets.append(text)
    return entries


def _split_identity(claims: list[str]) -> tuple[str | None, str | None]:
    """Pull the candidate's name out of their contact line so it can be the
    largest thing on the page. The name is whatever precedes the first comma
    or pipe -- the rest is contact detail."""
    if not claims:
        return None, None
    head, *rest = claims
    parts = re.split(r"\s*[|,]\s*", head.strip(), maxsplit=1)
    name = parts[0].strip() or None
    trailing = [parts[1].strip()] if len(parts) > 1 and parts[1].strip() else []
    contact_line = " | ".join(trailing + [claim.strip() for claim in rest]) or None
    return name, contact_line


def _structure(document: TailoredCv) -> tuple[str | None, str | None, list[_Section]]:
    name: str | None = None
    contact_line: str | None = None
    sections: list[_Section] = []

    for section in document.sections:
        claims = [claim.text for claim in section.claims]
        if _CONTACT_SECTION_RE.search(section.name) and name is None:
            name, contact_line = _split_identity(claims)
            continue
        if _PROSE_SECTION_RE.search(section.name):
            sections.append(_Section(name=section.name, layout="prose", paragraphs=claims))
        elif any(_looks_like_role_heading(text) for text in claims):
            sections.append(_Section(name=section.name, layout="entries", entries=_group_into_entries(claims)))
        else:
            sections.append(_Section(name=section.name, layout="list", items=claims))

    return name, contact_line, sections


def render_cv_pdf(document: TailoredCv) -> bytes:
    name, contact_line, sections = _structure(document)
    html = _env.get_template("cv.html").render(name=name, contact_line=contact_line, sections=sections)
    return HTML(string=html).write_pdf()


def render_cover_letter_pdf(document: TailoredCv) -> bytes:
    # Reuses the CV's contact section for the letterhead so the two documents
    # in one application share an identity block.
    name, contact_line, _ = _structure(document)
    html = _env.get_template("cover_letter.html").render(
        name=name,
        contact_line=contact_line,
        paragraphs=[claim.text for claim in document.cover_letter],
        closing=document.cover_letter_closing,
    )
    return HTML(string=html).write_pdf()


def render_master_cv_pdf(extracted_text: str) -> bytes:
    """Create an attachment-safe PDF when a master CV was uploaded as DOCX/TXT."""
    html = _env.get_template("master_cv.html").render(extracted_text=extracted_text)
    return HTML(string=html).write_pdf()
