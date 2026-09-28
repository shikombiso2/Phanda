import unittest

from app.listings.ingestion.skills import extract_required_skills


class SkillExtractionTests(unittest.TestCase):
    def test_word_boundaries_prevent_substring_false_positives(self):
        """Regression coverage: naive substring matching used to tag "word"
        out of "keyword" and "wordpress"."""
        skills = extract_required_skills("Requires keyword research and a WordPress developer")
        self.assertNotIn("word", skills)

    def test_aliases_resolve_to_the_canonical_skill(self):
        skills = extract_required_skills("Must be proficient in MS Excel and Microsoft Word")
        self.assertIn("excel", skills)
        self.assertIn("word", skills)

    def test_multi_word_alias_matches_as_one_unit(self):
        skills = extract_required_skills("Previous call centre experience required")
        self.assertIn("call centre", skills)

    def test_administration_is_a_legitimate_alias_of_admin(self):
        """Unlike the old substring bug, this is a deliberate alias, not a
        false positive: "administration duties" genuinely implies admin
        skills, and it only matches because it's listed as a whole-word
        alias, not because "admin" happens to be a substring of the word."""
        self.assertIn("admin", extract_required_skills("General office administration duties"))

    def test_returns_no_duplicates_when_multiple_aliases_match(self):
        skills = extract_required_skills("Excel, MS Excel and Microsoft Excel all required")
        self.assertEqual(skills.count("excel"), 1)

    def test_case_insensitive(self):
        self.assertIn("forklift", extract_required_skills("FORKLIFT license required"))

    def test_no_matches_returns_empty_list(self):
        self.assertEqual(extract_required_skills("A role about nothing in particular"), [])

    def test_vague_soft_skill_phrases_are_never_extracted(self):
        """These are generic praise any candidate could claim, not a concrete
        line item someone could put on a CV -- confirmed live bug where
        "problem solving" showed up as a user's only "missing skill"."""
        text = (
            "Looking for someone with great problem solving, teamwork, "
            "communication, time management, attention to detail, work ethic, "
            "leadership, adaptability, multitasking, interpersonal skills; "
            "must be hard working and a fast learner."
        )
        skills = extract_required_skills(text)
        for excluded in [
            "problem solving",
            "teamwork",
            "communication",
            "time management",
            "attention to detail",
            "work ethic",
            "leadership",
            "adaptability",
            "multitasking",
            "interpersonal skills",
            "hard working",
            "fast learner",
        ]:
            self.assertNotIn(excluded, skills)

    def test_concrete_skills_still_extracted_despite_soft_skill_exclusions(self):
        skills = extract_required_skills("Requires customer service, Excel and Python")
        self.assertIn("customer service", skills)
        self.assertIn("excel", skills)
        self.assertIn("python", skills)

    def test_education_level_phrasings_resolve_to_their_canonical_tags(self):
        """Confirmed live: these were being scanned but silently dropped for
        lack of any matching vocabulary entry, not a text-scanning gap."""
        self.assertIn("matric", extract_required_skills("Grade 12 completed plus a tertiary qualification"))
        self.assertIn("matric", extract_required_skills("Must have a National Senior Certificate"))
        self.assertIn("grade 10", extract_required_skills("Grade 10 or ABET Level 4"))
        self.assertIn("abet level 4", extract_required_skills("Grade 10 or ABET Level 4"))
        self.assertIn("degree", extract_required_skills("Requires a Bachelor's Degree in Accounting"))
        self.assertIn("honours degree", extract_required_skills("An Honours degree is required"))
        self.assertIn("postgraduate", extract_required_skills("A Master's degree is an advantage"))

    def test_education_levels_are_distinct_not_aliases_of_one_tag(self):
        # A candidate whose CV states matric doesn't satisfy a stated degree
        # requirement -- these must resolve to two separate canonical tags,
        # not collapse into one "education" tag that would silently claim a
        # match that isn't real.
        skills = extract_required_skills("Requires a Degree; Grade 12 alone is not sufficient")
        self.assertIn("degree", skills)
        self.assertIn("matric", skills)
        self.assertNotEqual("degree", "matric")

    def test_years_of_experience_phrasings_are_flagged(self):
        self.assertIn("years of experience", extract_required_skills("2 years experience in a similar role"))
        self.assertIn("years of experience", extract_required_skills("Requires 3 years' experience"))
        self.assertIn(
            "years of experience", extract_required_skills("Gain 1–2 years of relevant work experience")
        )
        self.assertIn(
            "years of experience",
            extract_required_skills("A minimum of two (2) years' experience in a legal environment"),
        )

    def test_no_years_of_experience_flag_when_none_is_stated(self):
        self.assertNotIn("years of experience", extract_required_skills("No prior experience necessary"))

    def test_report_writing_and_research_are_extracted_as_concrete_skills(self):
        skills = extract_required_skills("Must have strong report writing skills and be skilled in conducting research")
        self.assertIn("report writing", skills)
        self.assertIn("research", skills)


if __name__ == "__main__":
    unittest.main()
