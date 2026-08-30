import unittest

from app.core.models import ApplyMethod, ListingType
from app.listings.ingestion.normalize import classify_apply_target, classify_listing_type, normalize_adzuna


class NormalizeTests(unittest.TestCase):
    def test_email_apply_takes_precedence_when_email_is_in_description(self):
        method, target = classify_apply_target("https://example.com/apply", "Send your CV to jobs@example.co.za")

        self.assertEqual(method, ApplyMethod.email)
        self.assertEqual(target, "jobs@example.co.za")

    def test_url_apply_is_required_for_ats_link(self):
        method, target = classify_apply_target("https://example.com/apply", "Apply online")

        self.assertEqual(method, ApplyMethod.ats_link)
        self.assertEqual(target, "https://example.com/apply")

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
                "description": "Needs Excel and communication skills",
                "redirect_url": "https://adzuna.example/job",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "Cape Town"},
                "salary_min": 5000.0,
                "salary_max": 8000.0,
                "created": "2026-08-30T10:00:00Z",
            }
        )

        self.assertEqual(row.source, "adzuna")
        self.assertEqual(row.source_listing_id, "abc-123")
        self.assertEqual(row.apply_method, ApplyMethod.ats_link)
        self.assertEqual(row.required_skills, ["admin", "communication", "excel"])


if __name__ == "__main__":
    unittest.main()

