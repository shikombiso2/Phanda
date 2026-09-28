import unittest

from app.cv_tailoring.renderer import (
    _group_into_entries,
    _looks_like_role_heading,
    _split_identity,
    _split_role_and_dates,
    _structure,
    render_cover_letter_pdf,
    render_cv_pdf,
    render_master_cv_pdf,
)
from app.cv_tailoring.schemas import CvClaim, CvSection, TailoredCv


def _claim(text: str) -> CvClaim:
    return CvClaim(text=text, source_fact_ids=["fact_1"])


def _document() -> TailoredCv:
    """Shaped like a real generated draft, section names and all."""
    return TailoredCv(
        sections=[
            CvSection(name="Personal Details", claims=[
                _claim("Thandiwe Nkosi, Johannesburg, Gauteng, 071 234 5678, thandiwe.nkosi@email.com"),
            ]),
            CvSection(name="Professional Summary", claims=[
                _claim("Detail-oriented administrative professional with a National Senior Certificate."),
            ]),
            CvSection(name="Education", claims=[
                _claim("National Senior Certificate (Matric), Greenside High School, Johannesburg (2022)"),
            ]),
            CvSection(name="Professional Experience", claims=[
                _claim("Administrative Assistant (Internship) at Old Mutual, Sandton (Feb 2023 - Dec 2023)"),
                _claim("Captured and updated client records in Microsoft Excel."),
                _claim("Answered incoming calls and directed queries to the correct department."),
                _claim("Sales Assistant at Pick n Pay, Rosebank (Jan 2024 - Present)"),
                _claim("Maintained stock levels using Excel spreadsheets."),
            ]),
            CvSection(name="Skills", claims=[_claim("Microsoft Excel"), _claim("Microsoft Word")]),
        ],
        cover_letter=[_claim("I am writing to express my interest in the role.")],
        cover_letter_closing="Kind regards, Thandiwe Nkosi",
    )


class RoleHeadingDetectionTests(unittest.TestCase):
    def test_date_range_marks_a_role_heading(self):
        self.assertTrue(_looks_like_role_heading("Sales Assistant at Pick n Pay (Jan 2024 - Present)"))
        self.assertTrue(_looks_like_role_heading("Admin Assistant at Old Mutual (Feb 2023 - Dec 2023)"))

    def test_a_bare_year_is_not_a_role_heading(self):
        """An education line ends in "(2022)" and must stay a bullet rather
        than being promoted to a role heading."""
        self.assertFalse(_looks_like_role_heading("National Senior Certificate (Matric), Greenside High (2022)"))

    def test_a_non_date_parenthetical_is_not_a_role_heading(self):
        self.assertFalse(_looks_like_role_heading("Captured records in Microsoft Excel (accurately)"))

    def test_dates_are_peeled_off_for_secondary_styling(self):
        heading, dates = _split_role_and_dates("Administrative Assistant (Internship) at Old Mutual (Feb 2023 - Dec 2023)")
        self.assertEqual(dates, "Feb 2023 - Dec 2023")
        self.assertIn("Old Mutual", heading)
        self.assertNotIn("Feb 2023", heading)

    def test_a_line_with_no_dates_is_returned_unchanged(self):
        heading, dates = _split_role_and_dates("Sales Assistant at Pick n Pay")
        self.assertEqual(heading, "Sales Assistant at Pick n Pay")
        self.assertIsNone(dates)


class GroupingTests(unittest.TestCase):
    def test_claims_group_under_the_role_heading_above_them(self):
        entries = _group_into_entries([
            "Admin Assistant at Old Mutual (Feb 2023 - Dec 2023)",
            "Captured records.",
            "Answered calls.",
            "Sales Assistant at Pick n Pay (Jan 2024 - Present)",
            "Maintained stock levels.",
        ])
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].dates, "Feb 2023 - Dec 2023")
        self.assertEqual(entries[0].bullets, ["Captured records.", "Answered calls."])
        self.assertEqual(entries[1].bullets, ["Maintained stock levels."])

    def test_claims_before_any_heading_are_kept_not_dropped(self):
        entries = _group_into_entries(["Orphan bullet.", "Sales Assistant (Jan 2024 - Present)", "Real bullet."])
        self.assertIsNone(entries[0].heading)
        self.assertEqual(entries[0].bullets, ["Orphan bullet."])
        self.assertEqual(entries[1].bullets, ["Real bullet."])


class IdentityTests(unittest.TestCase):
    def test_name_is_split_from_the_contact_line(self):
        name, contact = _split_identity(["Thandiwe Nkosi, Johannesburg, Gauteng, 071 234 5678"])
        self.assertEqual(name, "Thandiwe Nkosi")
        self.assertEqual(contact, "Johannesburg, Gauteng, 071 234 5678")

    def test_a_name_with_no_contact_detail_still_works(self):
        name, contact = _split_identity(["Thandiwe Nkosi"])
        self.assertEqual(name, "Thandiwe Nkosi")
        self.assertIsNone(contact)


class StructureTests(unittest.TestCase):
    def test_sections_are_classified_by_intent(self):
        name, contact, sections = _structure(_document())
        self.assertEqual(name, "Thandiwe Nkosi")
        self.assertIn("071 234 5678", contact)
        layouts = {section.name: section.layout for section in sections}
        self.assertEqual(layouts["Professional Summary"], "prose")
        self.assertEqual(layouts["Professional Experience"], "entries")
        self.assertEqual(layouts["Skills"], "list")
        self.assertEqual(layouts["Education"], "list")

    def test_the_contact_section_becomes_the_header_not_a_body_section(self):
        _, _, sections = _structure(_document())
        self.assertNotIn("Personal Details", [section.name for section in sections])

    def test_a_document_with_no_contact_section_still_renders(self):
        document = TailoredCv(
            sections=[CvSection(name="Skills", claims=[_claim("Microsoft Excel")])],
            cover_letter=[_claim("Hello")],
            cover_letter_closing="Kind regards",
        )
        name, contact, sections = _structure(document)
        self.assertIsNone(name)
        self.assertIsNone(contact)
        self.assertEqual(len(sections), 1)


class PdfOutputTests(unittest.TestCase):
    def test_cv_renders_a_pdf(self):
        self.assertTrue(render_cv_pdf(_document()).startswith(b"%PDF-"))

    def test_cover_letter_renders_a_pdf(self):
        self.assertTrue(render_cover_letter_pdf(_document()).startswith(b"%PDF-"))

    def test_master_docx_or_text_fallback_is_a_pdf(self):
        pdf = render_master_cv_pdf("Candidate Name\nPython developer with two years of experience.")
        self.assertTrue(pdf.startswith(b"%PDF-"))

    def test_model_supplied_markup_characters_cannot_break_the_document(self):
        """Every string here came back from a language model; an unescaped
        "<" or "&" must not corrupt the markup or swallow text."""
        document = TailoredCv(
            sections=[
                CvSection(name="Skills", claims=[_claim("Research & <Development> reporting")]),
            ],
            cover_letter=[_claim("Costs & <margins> reviewed")],
            cover_letter_closing="Kind regards, A & B",
        )
        self.assertTrue(render_cv_pdf(document).startswith(b"%PDF-"))
        self.assertTrue(render_cover_letter_pdf(document).startswith(b"%PDF-"))
