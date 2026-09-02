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


if __name__ == "__main__":
    unittest.main()
