import unittest
from types import SimpleNamespace

from app.core.models import ApplyMethod, ExperienceLevel, JobType, ListingType
from app.recommendations.service import build_match_explanation


def profile(**overrides) -> SimpleNamespace:
    defaults = dict(
        skills=[], industries=[], location=None, open_to_remote=False,
        job_type=JobType.any, experience_level=ExperienceLevel.none,
        desired_salary_min=None, desired_salary_max=None,
    )
    return SimpleNamespace(**{**defaults, **overrides})


def listing(**overrides) -> SimpleNamespace:
    defaults = dict(
        title="Junior Admin Assistant", description="Entry-level admin role", required_skills=[],
        listing_type=ListingType.job, location=None, category=None, salary_min=None, salary_max=None,
        apply_method=ApplyMethod.ats_link, apply_target="https://example.test",
    )
    return SimpleNamespace(**{**defaults, **overrides})


class BuildMatchExplanationTests(unittest.TestCase):
    def test_strong_match_scores_well_above_neutral(self):
        candidate = profile(skills=["excel", "communication", "admin"], job_type=JobType.full_time, location="Johannesburg", experience_level=ExperienceLevel.none)
        job = listing(
            title="Junior Admin Assistant", description="Entry-level admin role requiring Excel and communication",
            required_skills=["excel", "communication", "admin"], listing_type=ListingType.job, location="Johannesburg",
        )
        explanation = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        self.assertGreater(explanation.score, 65)
        self.assertEqual(explanation.missing_skills, [])
        self.assertIn("skills", [f.key for f in explanation.factors])

    def test_poor_match_scores_well_below_neutral(self):
        candidate = profile(skills=["forklift", "warehouse"], job_type=JobType.internship, location="Cape Town", experience_level=ExperienceLevel.none)
        job = listing(
            title="Senior Financial Manager", description="Requires a senior finance manager with accounting expertise",
            required_skills=["accounting", "budgeting", "tax"], listing_type=ListingType.job, location="Durban",
        )
        explanation = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        self.assertLess(explanation.score, 35)
        self.assertEqual(explanation.missing_skills, ["accounting", "budgeting", "tax"])

    def test_bare_new_profile_scores_near_neutral_not_zero(self):
        """A brand-new user with an empty profile is the true cold-start
        case: every factor should fall back to neutral evidence rather than
        the listing scoring as an outright bad (or falsely great) match."""
        candidate = profile()
        job = listing(required_skills=["excel", "communication"])
        explanation = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        self.assertGreater(explanation.score, 35)
        self.assertLess(explanation.score, 65)

    def test_engagement_factor_is_absent_for_a_user_with_no_history(self):
        candidate = profile()
        job = listing(required_skills=["excel"])
        explanation = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        self.assertNotIn("engagement", [f.key for f in explanation.factors])

    def test_engagement_factor_appears_when_history_exists(self):
        candidate = profile()
        job = listing(required_skills=["excel"])
        explanation = build_match_explanation(candidate, job, engaged_skills={"excel"}, cv_skills=[])
        self.assertIn("engagement", [f.key for f in explanation.factors])

    def test_summary_mentions_missing_skills_when_nothing_else_is_strong(self):
        # A title/description with no seniority keyword ("junior", "senior",
        # etc.) keeps the experience factor neutral, isolating skills as the
        # only non-neutral factor for this assertion.
        candidate = profile()
        job = listing(title="Retail Assistant Role", description="General retail duties", required_skills=["excel", "sql", "python"])
        explanation = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        self.assertIn("Missing", explanation.summary)

    def test_score_is_deterministic(self):
        candidate = profile(skills=["excel"], location="Cape Town")
        job = listing(required_skills=["excel"], location="Cape Town")
        first = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        second = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        self.assertEqual(first.score, second.score)

    def test_profile_skills_and_cv_skills_are_unioned_in_the_response(self):
        # profile has "excel", the CV has "python" (never typed into the
        # profile), the listing wants both -- the response should show both
        # as matched, with no way for the client to tell which source
        # either one came from.
        candidate = profile(skills=["excel"])
        job = listing(required_skills=["excel", "python"])
        explanation = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=["python"])
        self.assertEqual(explanation.matched_skills, ["excel", "python"])
        self.assertEqual(explanation.missing_skills, [])

    def test_no_cv_or_a_not_ready_cv_contributes_nothing_not_an_error(self):
        candidate = profile(skills=["excel"])
        job = listing(required_skills=["excel", "python"])
        explanation = build_match_explanation(candidate, job, engaged_skills=set(), cv_skills=[])
        self.assertEqual(explanation.matched_skills, ["excel"])
        self.assertEqual(explanation.missing_skills, ["python"])


if __name__ == "__main__":
    unittest.main()
