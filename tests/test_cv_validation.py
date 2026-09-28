import unittest

from app.cv_tailoring.schemas import AnalysisPlan, CandidateFact, CandidateFacts, CvClaim, CvSection, JobRequirement, JobRequirements, MatchingStrategy, SourceSpan, TailoredCv
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
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])],
            cover_letter_closing="Kind regards, Test Candidate",
        )
        codes = {issue.code for issue in validate_tailored_cv(draft, self.facts, [])}
        self.assertIn("unsupported_metric", codes)
        self.assertIn("unsupported_employer", codes)
        self.assertIn("unsupported_job_title", codes)

    def test_rejects_unsupported_skill_and_qualification(self):
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Bachelor degree holder", source_fact_ids=["fact_experience"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python, Kubernetes", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])],
            cover_letter_closing="Kind regards, Test Candidate",
        )
        codes = {issue.code for issue in validate_tailored_cv(draft, self.facts, [])}
        self.assertIn("unsupported_qualification", codes)
        self.assertIn("unsupported_skill", codes)

    def test_rejects_unknown_fact_id(self):
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Python", source_fact_ids=["fact_unknown"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])],
            cover_letter_closing="Kind regards, Test Candidate",
        )
        self.assertIn("unknown_fact_id", {issue.code for issue in validate_tailored_cv(draft, self.facts, [])})

    def test_claim_echoing_the_job_listings_own_terminology_is_not_fabrication(self):
        """Tailoring means echoing the employer's wording back at them. That
        phrase is grounded in the listing even though it is absent from the
        candidate's own CV, so it must not score as an invented name."""
        requirements = [JobRequirement(id="job_1", category="knowledge", text="Knowledge of Asset Management Framework and Treasury Regulations")]
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Ready to support Asset Management work", source_fact_ids=["fact_experience"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])],
            cover_letter_closing="Kind regards, Test Candidate",
        )
        codes = {issue.code for issue in validate_tailored_cv(draft, self.facts, requirements)}
        self.assertNotIn("unsupported_named_claim", codes)

    def test_named_claim_in_neither_the_cv_nor_the_listing_is_still_rejected(self):
        requirements = [JobRequirement(id="job_1", category="knowledge", text="Knowledge of Asset Management Framework")]
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Led the Global Excellence Programme", source_fact_ids=["fact_experience"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])],
            cover_letter_closing="Kind regards, Test Candidate",
        )
        codes = {issue.code for issue in validate_tailored_cv(draft, self.facts, requirements)}
        self.assertIn("unsupported_named_claim", codes)

    def test_listing_wording_never_authorises_a_qualification_the_candidate_lacks(self):
        """The widened evidence pool is for naming only. A listing asking for
        a diploma is not evidence the candidate holds one."""
        requirements = [JobRequirement(id="job_1", category="education", text="A post-matric diploma in Supply Chain Management")]
        draft = TailoredCv(
            sections=[
                CvSection(name="Professional Summary", claims=[CvClaim(text="Holds a diploma in logistics", source_fact_ids=["fact_experience"])]),
                CvSection(name="Skills", claims=[CvClaim(text="Python", source_fact_ids=["fact_skill"])]),
            ],
            cover_letter=[CvClaim(text="Python", source_fact_ids=["fact_skill"])],
            cover_letter_closing="Kind regards, Test Candidate",
        )
        codes = {issue.code for issue in validate_tailored_cv(draft, self.facts, requirements)}
        self.assertIn("unsupported_qualification", codes)


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


# Modelled on the real confirmed bug: a job header followed by five
# achievement bullets, and a skills list of six items -- all collapsed by
# CV text extraction into one whitespace-joined string with no newlines
# (see app/cv_tailoring/extraction.py's _usable_text), exactly the shape
# validate_analysis actually receives in production.
_HEADER = "Sales Assistant Jan 2024 - Present Pick n Pay - Rosebank, Johannesburg "
_BULLETS = (
    "Provided friendly, efficient customer service to an average of 80 customers per shift. "
    "Processed cash and card transactions accurately using the point-of-sale system. "
    "Maintained stock levels and assisted with weekly inventory counts using Excel spreadsheets. "
    "Resolved customer queries and complaints calmly, escalating where necessary. "
    "Trained two new team members on till procedures and store policies. "
)
_SKILLS_SECTION = (
    "SKILLS Microsoft Excel (spreadsheets, basic formulas, data entry) Microsoft Word Customer service "
    "Communication (written and verbal) Cash handling and point-of-sale systems Teamwork and time management "
    "REFERENCES Available on request."
)
_UNDER_EXTRACTED_SOURCE = _HEADER + _BULLETS + _SKILLS_SECTION


class CompletenessValidationTests(unittest.TestCase):
    def test_header_only_experience_fact_with_five_real_bullets_is_flagged_incomplete(self):
        # Reproduces the confirmed bug exactly: one experience fact covering
        # only the job title/company/dates header, none of the five
        # achievement bullets that follow it turned into their own facts.
        header_excerpt = _HEADER.strip()
        start = _UNDER_EXTRACTED_SOURCE.index(header_excerpt)
        plan = AnalysisPlan(
            candidate_facts=CandidateFacts(
                facts=[
                    CandidateFact(
                        id="fact_1", category="experience", normalized_value=header_excerpt,
                        source_spans=[SourceSpan(start=start, end=start + len(header_excerpt), excerpt=header_excerpt)],
                        confidence=1,
                    )
                ]
            ),
            job_requirements=JobRequirements(requirements=[]),
            strategy=MatchingStrategy(),
        )
        issues = validate_analysis(plan, _UNDER_EXTRACTED_SOURCE)
        self.assertIn("incomplete_experience_extraction", {issue.code for issue in issues})

    def test_two_of_six_missing_skills_is_flagged_incomplete(self):
        skill_excerpts = ["Microsoft Excel", "Microsoft Word", "Customer service", "Communication"]
        facts = [
            CandidateFact(
                id=f"fact_skill_{i}", category="skill", normalized_value=excerpt,
                source_spans=[
                    SourceSpan(
                        start=_UNDER_EXTRACTED_SOURCE.index(excerpt),
                        end=_UNDER_EXTRACTED_SOURCE.index(excerpt) + len(excerpt),
                        excerpt=excerpt,
                    )
                ],
                confidence=1,
            )
            for i, excerpt in enumerate(skill_excerpts)
        ]
        plan = AnalysisPlan(
            candidate_facts=CandidateFacts(facts=facts),
            job_requirements=JobRequirements(requirements=[]),
            strategy=MatchingStrategy(),
        )
        issues = validate_analysis(plan, _UNDER_EXTRACTED_SOURCE)
        self.assertIn("incomplete_skill_extraction", {issue.code for issue in issues})

    def test_fully_extracted_plan_is_not_flagged(self):
        # The fix working as intended: a header fact plus one fact per
        # bullet, and one fact per skill -- no completeness issue.
        facts = []
        header_excerpt = _HEADER.strip()
        header_start = _UNDER_EXTRACTED_SOURCE.index(header_excerpt)
        facts.append(
            CandidateFact(
                id="fact_header", category="experience", normalized_value=header_excerpt,
                source_spans=[SourceSpan(start=header_start, end=header_start + len(header_excerpt), excerpt=header_excerpt)],
                confidence=1,
            )
        )
        bullets = [
            "Provided friendly, efficient customer service to an average of 80 customers per shift.",
            "Processed cash and card transactions accurately using the point-of-sale system.",
            "Maintained stock levels and assisted with weekly inventory counts using Excel spreadsheets.",
            "Resolved customer queries and complaints calmly, escalating where necessary.",
            "Trained two new team members on till procedures and store policies.",
        ]
        for i, bullet in enumerate(bullets):
            idx = _UNDER_EXTRACTED_SOURCE.index(bullet)
            facts.append(
                CandidateFact(
                    id=f"fact_bullet_{i}", category="experience", normalized_value=bullet,
                    source_spans=[SourceSpan(start=idx, end=idx + len(bullet), excerpt=bullet)], confidence=1,
                )
            )
        for i, skill in enumerate([
            "Microsoft Excel (spreadsheets, basic formulas, data entry)",
            "Microsoft Word",
            "Customer service",
            "Communication (written and verbal)",
            "Cash handling and point-of-sale systems",
            "Teamwork and time management",
        ]):
            idx = _UNDER_EXTRACTED_SOURCE.index(skill)
            facts.append(
                CandidateFact(
                    id=f"fact_skill_{i}", category="skill", normalized_value=skill,
                    source_spans=[SourceSpan(start=idx, end=idx + len(skill), excerpt=skill)], confidence=1,
                )
            )
        plan = AnalysisPlan(
            candidate_facts=CandidateFacts(facts=facts),
            job_requirements=JobRequirements(requirements=[]),
            strategy=MatchingStrategy(),
        )
        issues = validate_analysis(plan, _UNDER_EXTRACTED_SOURCE)
        codes = {issue.code for issue in issues}
        self.assertNotIn("incomplete_experience_extraction", codes)
        self.assertNotIn("incomplete_skill_extraction", codes)
