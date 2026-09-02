import unittest

from app.cv_tailoring.schemas import CandidateFact, CvClaim, CvSection, SourceSpan, TailoredCv
from app.cv_tailoring.validation import validate_tailored_cv


def fact(fact_id: str, category: str, excerpt: str) -> CandidateFact:
    return CandidateFact(
        id=fact_id, category=category, normalized_value=excerpt,
        source_spans=[SourceSpan(start=0, end=len(excerpt), excerpt=excerpt)], confidence=1,
    )


class TailoredCvValidationTests(unittest.TestCase):
    def setUp(self):
        self.facts = [
            fact("fact_experience", "experience", "ABC Company Software Developer Python 2 years 2024"),
            fact("fact_skill", "skill", "Python"),
        ]

    def test_rejects_fabricated_employer_date_metric_and_title(self):
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Senior Engineer at XYZ Company with 5 years experience in 2022", source_fact_ids=["fact_experience"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]
        )
        codes = {issue.code for issue in validate_tailored_cv(draft, self.facts, set())}
        self.assertIn("unsupported_metric", codes)
        self.assertIn("unsupported_employer", codes)
        self.assertIn("unsupported_job_title", codes)

    def test_rejects_unsupported_skill_and_qualification(self):
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Bachelor degree holder", source_fact_ids=["fact_experience"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python, Kubernetes", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]
        )
        codes = {issue.code for issue in validate_tailored_cv(draft, self.facts, set())}
        self.assertIn("unsupported_qualification", codes)
        self.assertIn("unsupported_skill", codes)

    def test_rejects_unknown_fact_id(self):
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Python", source_fact_ids=["fact_unknown"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]
        )
        self.assertIn("unknown_fact_id", {issue.code for issue in validate_tailored_cv(draft, self.facts, set())})
