import unittest

from app.cv_tailoring.renderer import render_master_cv_pdf


class RendererTests(unittest.TestCase):
    def test_master_docx_or_text_fallback_is_a_pdf(self):
        pdf = render_master_cv_pdf("Candidate Name\nPython developer with two years of experience.")
        self.assertTrue(pdf.startswith(b"%PDF-"))
