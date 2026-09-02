from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.cv_tailoring.schemas import TailoredCv


def render_cv_pdf(document: TailoredCv) -> bytes:
    return _render([(section.name, [claim.text for claim in section.claims]) for section in document.sections])


def render_cover_letter_pdf(document: TailoredCv) -> bytes:
    return _render([("Cover Letter", [claim.text for claim in document.cover_letter])])


def render_master_cv_pdf(extracted_text: str) -> bytes:
    """Create an attachment-safe PDF when a master CV was uploaded as DOCX/TXT."""
    return _render([("Master CV", [extracted_text])])


def _render(sections: list[tuple[str, list[str]]]) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    output = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.7 * cm, rightMargin=1.7 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story = []
    for name, claims in sections:
        story.append(Paragraph(escape(name), styles["Heading2"]))
        for claim in claims:
            story.append(Paragraph(escape(claim), styles["BodyText"]))
        story.append(Spacer(1, 8))
    output.build(story)
    return buffer.getvalue()
