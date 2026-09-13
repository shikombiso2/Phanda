import unittest

from app.cv_tailoring.schemas import AnalysisPlan, CandidateFact, CandidateFacts, CvClaim, CvSection, JobRequirements, MatchingStrategy, SourceSpan, TailoredCv
from app.cv_tailoring.validation import validate_analysis, validate_tailored_cv


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


def _plan(excerpt: str, start: int, end: int) -> AnalysisPlan:
    return AnalysisPlan(
        candidate_facts=CandidateFacts(
            facts=[
                CandidateFact(
                    id="fact_1", category="experience", normalized_value=excerpt,
                    source_spans=[SourceSpan(start=start, end=end, excerpt=excerpt)], confidence=1,
                )
            ]
        ),
        job_requirements=JobRequirements(requirements=[]),
        strategy=MatchingStrategy(),
    )


class AnalysisValidationTests(unittest.TestCase):
    def test_excerpt_present_with_wrong_offsets_is_located_by_search_and_corrected(self):
        source_text = "Grants Administrator, University of the Witwatersrand, Johannesburg (2021-Present)"
        excerpt = "University of the Witwatersrand"
        true_start = source_text.index(excerpt)
        true_end = true_start + len(excerpt)

        plan = _plan(excerpt, start=true_start + 2, end=true_end - 2)
        issues = validate_analysis(plan, source_text)

        self.assertEqual(issues, [])
        span = plan.candidate_facts.facts[0].source_spans[0]
        self.assertEqual(span.start, true_start)
        self.assertEqual(span.end, true_end)

    def test_excerpt_absent_from_cv_still_fails_as_source_excerpt_mismatch(self):
        source_text = "Grants Administrator, University of the Witwatersrand, Johannesburg (2021-Present)"
        plan = _plan("Chief Executive Officer, Acme Corp", start=0, end=35)

        issues = validate_analysis(plan, source_text)

        self.assertEqual([issue.code for issue in issues], ["source_excerpt_mismatch"])
