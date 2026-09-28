import unittest

from app.core.models import ApplyMethod, ListingType
from app.listings.ingestion.normalize import classify_apply_target, classify_listing_type, normalize_adzuna


class NormalizeTests(unittest.TestCase):
    def test_untrusted_description_text_is_never_used_as_an_apply_target(self):
        """An email address embedded in scraped/free-text description content
        must never become the apply target — only a source-verified,
        structured contact email may. Otherwise anything that can influence
        that text can redirect a candidate's CV to an address it chose."""
        method, target = classify_apply_target("https://example.com/apply")

        self.assertEqual(method, ApplyMethod.ats_link)
        self.assertEqual(target, "https://example.com/apply")

    def test_verified_contact_email_is_used_when_a_source_provides_one(self):
        method, target = classify_apply_target("https://example.com/apply", verified_contact_email="jobs@example.co.za")

        self.assertEqual(method, ApplyMethod.email)
        self.assertEqual(target, "jobs@example.co.za")

    def test_no_target_at_all_is_rejected(self):
        with self.assertRaises(ValueError):
            classify_apply_target(None)

    def test_listing_type_keywords(self):
        self.assertEqual(classify_listing_type("IT Learnership", ""), ListingType.learnership)
        self.assertEqual(classify_listing_type("Software Intern", ""), ListingType.internship)
        self.assertEqual(classify_listing_type("Artisan Apprentice", ""), ListingType.apprenticeship)
        self.assertEqual(classify_listing_type("Engineering Bursary", ""), ListingType.bursary)

    def test_adzuna_normalization_extracts_shared_schema(self):
        row = normalize_adzuna(
            {
                "id": "abc-123",
                "title": "Admin Assistant",
                "description": "Needs Excel and admin skills",
                "redirect_url": "https://adzuna.example/job",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "Cape Town"},
                "salary_min": 5000.0,
                "salary_max": 8000.0,
                "created": "2026-08-30T10:00:00Z",
                "category": {"tag": "admin-jobs", "label": "Admin Jobs"},
            }
        )

        self.assertEqual(row.source, "adzuna")
        self.assertEqual(row.source_listing_id, "abc-123")
        self.assertEqual(row.apply_method, ApplyMethod.ats_link)
        self.assertEqual(row.required_skills, ["admin", "excel"])
        self.assertEqual(row.category, "Admin Jobs")

    def test_missing_category_is_none_not_an_error(self):
        row = normalize_adzuna(
            {"id": "x", "title": "Role", "description": "d", "redirect_url": "https://example.test/apply"}
        )
        self.assertIsNone(row.category)


if __name__ == "__main__":
    unittest.main()

