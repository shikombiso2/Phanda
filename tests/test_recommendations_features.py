import unittest

from app.core.models import ExperienceLevel, JobType, ListingType
from app.recommendations import features


class SkillCompatibilityTests(unittest.TestCase):
    def test_full_overlap_scores_high(self):
        # Laplace/add-one smoothing -- (matched+1)/(required+2) -- means even
        # a perfect match on a small number of required skills stays a bit
        # under 1.0 (2/2 -> 0.75): appropriate humility about a small sample,
        # not a bug. It climbs toward 1.0 as the skill count grows (see the
        # next test).
        probability, matched, missing = features.skill_compatibility(["excel", "communication"], [], ["excel", "communication"])
        self.assertGreater(probability, 0.7)
        self.assertEqual(matched, ["communication", "excel"])
        self.assertEqual(missing, [])

    def test_full_overlap_approaches_one_as_required_skill_count_grows(self):
        skills = ["excel", "communication", "admin", "sales", "typing", "filing", "reception", "invoicing"]
        probability, _, missing = features.skill_compatibility(skills, [], skills)
        self.assertGreater(probability, 0.85)
        self.assertEqual(missing, [])

    def test_no_overlap_scores_low_but_not_zero(self):
        probability, matched, missing = features.skill_compatibility(["forklift"], [], ["excel"])
        self.assertGreater(probability, 0.0)
        self.assertLess(probability, 0.4)
        self.assertEqual(missing, ["excel"])

    def test_untagged_listing_is_neutral_not_zero(self):
        """The old implementation returned score=0 for a listing with no
        tagged skills at all -- unfairly burying every under-tagged listing.
        Neutral (no evidence) is the honest answer."""
        probability, matched, missing = features.skill_compatibility(["excel"], [], [])
        self.assertEqual(probability, 0.5)
        self.assertEqual(matched, [])
        self.assertEqual(missing, [])

    def test_matching_is_case_and_whitespace_insensitive(self):
        probability, matched, _ = features.skill_compatibility([" Excel "], [], ["EXCEL"])
        self.assertEqual(matched, ["excel"])

    def test_one_missing_skill_out_of_several_still_scores_reasonably(self):
        probability, _, missing = features.skill_compatibility(
            ["excel", "communication", "admin"], [], ["excel", "communication", "admin", "sales"]
        )
        self.assertEqual(missing, ["sales"])
        self.assertGreater(probability, 0.6)

    def test_profile_and_cv_skills_are_unioned(self):
        # The exact case from the design brief: profile has "excel", the CV
        # has "python", the listing wants both -- both must show as matched,
        # not just whichever source happened to be checked first.
        probability, matched, missing = features.skill_compatibility(["excel"], ["python"], ["excel", "python"])
        self.assertEqual(matched, ["excel", "python"])
        self.assertEqual(missing, [])

    def test_cv_skill_alone_can_satisfy_a_requirement_profile_doesnt_state(self):
        _, matched, missing = features.skill_compatibility([], ["python"], ["python"])
        self.assertEqual(matched, ["python"])
        self.assertEqual(missing, [])

    def test_overlapping_profile_and_cv_skills_are_not_double_counted(self):
        probability, matched, _ = features.skill_compatibility(["excel"], ["excel"], ["excel"])
        self.assertEqual(matched, ["excel"])
        # (1+1)/(1+2) -- the same as a single source stating "excel" once,
        # not inflated by the skill appearing in both sources.
        self.assertAlmostEqual(probability, 2 / 3)


class ExperienceCompatibilityTests(unittest.TestCase):
    def test_exact_seniority_match_scores_high(self):
        probability, seniority = features.experience_compatibility(ExperienceLevel.none, "Junior Admin Assistant", "Entry-level role")
        self.assertEqual(seniority, 0)
        self.assertGreater(probability, 0.75)

    def test_opposite_extremes_score_low(self):
        probability, seniority = features.experience_compatibility(ExperienceLevel.none, "Senior Manager", "Requires senior leadership")
        self.assertEqual(seniority, 2)
        self.assertLess(probability, 0.3)

    def test_no_seniority_signal_is_neutral(self):
        probability, seniority = features.experience_compatibility(ExperienceLevel.some, "Cashier", "Retail role")
        self.assertIsNone(seniority)
        self.assertEqual(probability, 0.5)


class JobTypeCompatibilityTests(unittest.TestCase):
    def test_any_job_type_is_mildly_positive_everywhere(self):
        for listing_type in ListingType:
            self.assertEqual(features.job_type_compatibility(JobType.any, listing_type), 0.7)

    def test_full_time_matches_standard_jobs_well(self):
        self.assertGreater(features.job_type_compatibility(JobType.full_time, ListingType.job), 0.8)

    def test_internship_seeker_is_deprioritized_for_standard_jobs(self):
        self.assertLess(features.job_type_compatibility(JobType.internship, ListingType.job), 0.4)

    def test_internship_seeker_matches_internships_well(self):
        self.assertGreater(features.job_type_compatibility(JobType.internship, ListingType.internship), 0.85)


class LocationCompatibilityTests(unittest.TestCase):
    def test_matching_city_scores_high(self):
        self.assertGreater(features.location_compatibility("Johannesburg", False, "Johannesburg, Gauteng"), 0.8)

    def test_remote_open_and_remote_listing_scores_high(self):
        self.assertGreater(features.location_compatibility("Cape Town", True, "Remote"), 0.85)

    def test_different_cities_scores_low(self):
        self.assertLess(features.location_compatibility("Durban", False, "Cape Town"), 0.4)

    def test_missing_location_data_is_neutral(self):
        self.assertEqual(features.location_compatibility(None, False, "Cape Town"), 0.5)
        self.assertEqual(features.location_compatibility("Cape Town", False, None), 0.5)


class IndustryCompatibilityTests(unittest.TestCase):
    def test_matching_industry_scores_well(self):
        self.assertGreater(features.industry_compatibility(["retail"], "Retail & FMCG"), 0.6)

    def test_no_category_data_is_neutral(self):
        self.assertEqual(features.industry_compatibility(["retail"], None), 0.5)

    def test_no_profile_industries_is_neutral(self):
        self.assertEqual(features.industry_compatibility([], "IT Jobs"), 0.5)

    def test_unrelated_industry_scores_low(self):
        self.assertLess(features.industry_compatibility(["hospitality"], "IT Jobs"), 0.5)


class SalaryCompatibilityTests(unittest.TestCase):
    def test_no_data_either_side_is_neutral(self):
        self.assertEqual(features.salary_compatibility(None, None, None, None), 0.5)

    def test_listing_pays_less_than_desired_scores_low(self):
        self.assertLess(features.salary_compatibility(10000, 15000, 5000, 8000), 0.5)

    def test_overlapping_ranges_score_well(self):
        self.assertGreater(features.salary_compatibility(8000, 12000, 10000, 14000), 0.6)

    def test_listing_pays_more_than_desired_is_not_penalized(self):
        self.assertGreater(features.salary_compatibility(8000, 10000, 15000, 20000), 0.6)


class EngagementCompatibilityTests(unittest.TestCase):
    def test_no_engagement_history_is_not_applicable(self):
        probability, applicable = features.engagement_compatibility(["excel"], set())
        self.assertFalse(applicable)
        self.assertEqual(probability, 0.5)

    def test_overlapping_engagement_skills_boosts_probability(self):
        probability, applicable = features.engagement_compatibility(["excel", "admin"], {"excel", "admin"})
        self.assertTrue(applicable)
        self.assertGreater(probability, 0.7)

    def test_listing_with_no_required_skills_is_not_applicable(self):
        probability, applicable = features.engagement_compatibility([], {"excel"})
        self.assertFalse(applicable)


if __name__ == "__main__":
    unittest.main()
