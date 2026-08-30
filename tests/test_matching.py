import unittest
from types import SimpleNamespace

from app.matching.service import score_listing


class MatchingTests(unittest.TestCase):
    def test_score_listing_returns_explainable_breakdown(self):
        profile = SimpleNamespace(skills=["Excel", "Customer Service"])
        listing = SimpleNamespace(required_skills=["excel", "sales", "customer service"])

        result = score_listing(profile, listing)

        self.assertEqual(result["score"], 67)
        self.assertEqual(result["matched_skills"], ["customer service", "excel"])
        self.assertEqual(result["missing_skills"], ["sales"])

    def test_empty_required_skills_is_not_a_bare_number(self):
        profile = SimpleNamespace(skills=["excel"])
        listing = SimpleNamespace(required_skills=[])

        result = score_listing(profile, listing)

        self.assertEqual(result, {"score": 0, "matched_skills": [], "missing_skills": []})


if __name__ == "__main__":
    unittest.main()

