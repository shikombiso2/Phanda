import unittest

from app.core.models import ExperienceLevel, JobType, ListingType
from app.recommendations import features


class SkillCompatibilityTests(unittest.TestCase):
    def test_full_overlap_scores_high(self):
        # Plain proportion (matched/required), not Laplace-smoothed -- a
        # perfect match is exactly 1.0 regardless of how many skills were
        # required. See test_full_overlap_is_exactly_one_regardless_of_
        # required_skill_count for why: the old smoothed version made a
        # small-N perfect match (e.g. 1/1) score identically to a partial
        # large-N match (3/4), which mis-ranked genuinely stronger matches
        # below weaker ones.
        probability, matched, missing = features.skill_compatibility(["excel", "communication"], [], ["excel", "communication"])
        self.assertEqual(probability, 1.0)
        self.assertEqual(matched, ["communication", "excel"])
        self.assertEqual(missing, [])

    def test_full_overlap_is_exactly_one_regardless_of_required_skill_count(self):
        skills = ["excel", "communication", "admin", "sales", "typing", "filing", "reception", "invoicing"]
        probability, _, missing = features.skill_compatibility(skills, [], skills)
        self.assertEqual(probability, 1.0)
        self.assertEqual(missing, [])

    def test_coverage_is_ranked_correctly_across_different_required_counts(self):
        # The concrete bug this fix closes: under the old (matched+1)/
        # (required+2) formula, 1 matched of 1 required and 3 matched of 4
        # required scored IDENTICALLY (both (1+1)/(1+2) = (3+1)/(4+2) =
        # 2/3), and 4 matched of 6 required ((4+1)/(6+2) = 5/8 = 0.625)
        # scored WORSE than the trivial 1/1 case -- even though matching
        # four distinct required skills is stronger real evidence of fit
        # than matching one. A plain proportion ranks these correctly by
        # actual coverage: 100% > 75% > 66.7%.
        one_of_one, _, _ = features.skill_compatibility(["excel"], [], ["excel"])
        three_of_four, _, _ = features.skill_compatibility(
            ["excel", "communication", "admin"], [], ["excel", "communication", "admin", "sales"]
        )
        four_of_six, _, _ = features.skill_compatibility(
            ["excel", "communication", "admin", "sales"],
            [],
            ["excel", "communication", "admin", "sales", "typing", "filing"],
        )
        self.assertEqual(one_of_one, 1.0)
        self.assertEqual(three_of_four, 0.75)
        self.assertAlmostEqual(four_of_six, 2 / 3)
        self.assertGreater(one_of_one, three_of_four)
        self.assertGreater(three_of_four, four_of_six)

    def test_no_overlap_scores_zero_on_this_factor(self):
        # No longer smoothed away from zero -- a listing whose single stated
        # requirement the candidate entirely lacks gets a hard 0 on the
        # skills factor specifically. The overall listing score still isn't
        # zero (other weighted factors still contribute via the log-odds
        # pool in scoring.combine), this only changes the skills factor's
        # own contribution.
        probability, matched, missing = features.skill_compatibility(["forklift"], [], ["excel"])
        self.assertEqual(probability, 0.0)
        self.assertEqual(missing, ["excel"])

    def test_a_candidate_with_zero_stated_skills_is_neutral_not_a_confirmed_miss(self):
        # Distinct from the case above: "forklift" vs "excel" is a real,
        # stated skill that simply doesn't overlap -- a genuine 0.0 is
        # correct there. A candidate with NO skills recorded anywhere
        # (profile or CV) hasn't told us anything at all, which is the same
        # "no evidence" situation the empty-required-skills case already
        # protects -- it must not be scored as if they'd confirmed lacking
        # every requirement.
        probability, matched, missing = features.skill_compatibility([], [], ["excel", "communication"])
        self.assertEqual(probability, 0.5)
        self.assertEqual(matched, [])
        self.assertEqual(missing, ["communication", "excel"])

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
        # 1/1 -- the same as a single source stating "excel" once, not
        # inflated by the skill appearing in both sources.
        self.assertEqual(probability, 1.0)


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
