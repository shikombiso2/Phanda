"""Unit tests for the three confirmed structural bugs fixed while porting
phanda-scrapers/vacancyupdate_parser.py, plus the "Apply online" marker
apply-target logic that replaced heading-based lookup. Each fixture below
reproduces the exact real pattern observed in a live post (see
phanda-scrapers/scrape_output.txt), not a hypothetical case.
"""
import unittest

from app.core.models import ApplyMethod, ListingType
from app.listings.ingestion.vacancyupdate_adapter import parse_post


def _page(*, h1: str, body_html: str) -> str:
    return f"<html><body><h1>{h1}</h1><div class='entry-content'>{body_html}</div></body></html>"


class VacancyUpdateParserTests(unittest.TestCase):
    def test_company_name_strips_a_leading_the(self):
        # Real bug: the Clicks post's own "About" heading reads "About the
        # Clicks", not "About Clicks" -- captured verbatim as "the Clicks"
        # before this fix.
        html = _page(
            h1="Clicks Youth Employment Programme 2026",
            body_html=(
                "<p>About the Clicks</p><p>Clicks is one of South Africa's leading retailers.</p>"
                "<p>Apply online through the official portal:</p>"
                '<a href="https://clicks.example.com/apply">Youth Employment Programme</a>'
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/clicks-youth-employment-programme", html)
        self.assertEqual(listing.company, "Clicks")

    def test_location_capture_stops_at_the_first_line(self):
        # Real bug: "Based in\nSandton\n, this full-time learnership..."
        # bled the location capture into the following sentence because the
        # original character class's \s matched across the line break.
        html = _page(
            h1="Experian Consumer Care Learnership 2026",
            body_html=(
                "<p>About Experian</p><p>Experian is a global leader in data.</p>"
                "<p>Based in</p><p>Sandton</p><p>, this full-time learnership provides hands-on experience.</p>"
                "<p>Apply online:</p>"
                '<a href="https://experian.example.com/apply">Experian Consumer Care Learnership 2026</a>'
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/experian-consumer-care-learnership", html)
        self.assertEqual(listing.location, "Sandton")

    def test_location_label_form_stops_before_the_next_label(self):
        # Real bug: "Location:\nGauteng\nIndustry:\nFMCG..." captured
        # "Gauteng\nIndustry" as one string.
        html = _page(
            h1="Clicks Youth Employment Programme 2026",
            body_html=(
                "<p>About the Clicks</p><p>Clicks is a retailer.</p>"
                "<p>Location:</p><p>Gauteng</p><p>Industry:</p><p>FMCG, Retail</p>"
                "<p>Apply online:</p>"
                '<a href="https://clicks.example.com/apply">Youth Employment Programme</a>'
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/clicks-youth-employment-programme", html)
        self.assertEqual(listing.location, "Gauteng")
        self.assertEqual(listing.category, "FMCG, Retail")

    def test_closing_date_sentence_phrasing_with_internal_newline(self):
        # Real bug: "closing date on\n14 September\n2026" -- the date's own
        # day/month and year land on separate lines and must be
        # whitespace-normalized before parsing, not just captured raw.
        html = _page(
            h1="Metropolitan Human Capital Learnership 2026",
            body_html=(
                "<p>About Metropolitan Life</p><p>Metropolitan is a financial services provider.</p>"
                "<p>Apply online:</p>"
                '<a href="https://metropolitan.example.com/apply">Metropolitan Human Capital Learnership</a>'
                "<p>Closing Date</p>"
                "<p>Applications must be submitted before the closing date on</p>"
                "<p>14 September</p><p>2026</p><p>.</p>"
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/metropolitan-human-capital-learnership", html)
        self.assertIsNotNone(listing.expires_at)
        self.assertEqual((listing.expires_at.year, listing.expires_at.month, listing.expires_at.day), (2026, 9, 14))

    def test_closing_date_inline_label_phrasing_with_no_on(self):
        # Real bug: the Clicks post gives "(Closing Date:\n09 September
        # 2026\n)" inline in a paragraph, with no "on" and no dedicated
        # section -- the original "closing date ... on <date>" regex missed
        # this entirely.
        html = _page(
            h1="Clicks Youth Employment Programme 2026",
            body_html=(
                "<p>About the Clicks</p><p>Clicks is a retailer.</p>"
                "<p>Apply online through the official Clicks careers portal:</p>"
                '<a href="https://clicks.example.com/apply">Youth Employment Programme</a>'
                "<p>(Closing Date:</p><p>09 September 2026</p><p>)</p>"
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/clicks-youth-employment-programme", html)
        self.assertIsNotNone(listing.expires_at)
        self.assertEqual((listing.expires_at.year, listing.expires_at.month, listing.expires_at.day), (2026, 9, 9))

    def test_apply_target_found_via_apply_online_marker_not_a_heading(self):
        # Real gap beyond the 3 listed bugs: some posts have no
        # "Application Instructions"-style heading at all (Clicks uses plain
        # prose), but every sampled post does contain "Apply online"
        # immediately before the real link.
        html = _page(
            h1="Givaudan Customer Care Learnership 2026",
            body_html=(
                "<p>About Givaudan</p><p>Givaudan is a flavour and fragrance company.</p>"
                "<p>How to Apply</p>"
                "<p>Apply online:</p>"
                '<a href="https://givaudan.example.com/apply">Givaudan Customer Care Learnership 2026</a>'
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/givaudan-customer-care-learnership", html)
        self.assertEqual(listing.apply_method, ApplyMethod.ats_link)
        self.assertEqual(listing.apply_target, "https://givaudan.example.com/apply")

    def test_internal_vacancyupdate_links_before_the_marker_are_ignored(self):
        html = _page(
            h1="Vans Job as Sales Assistant 2026",
            body_html=(
                "<p>About Vans</p><p>Vans is a footwear brand.</p>"
                '<a href="https://vacancyupdate.co.za/other-post">Related post</a>'
                "<p>Apply online Vans Job as Sales Assistant 2026 at:</p>"
                '<a href="https://vans.example.com/apply">Apply here</a>'
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/vans-sales-assistant", html)
        self.assertEqual(listing.apply_target, "https://vans.example.com/apply")

    def test_no_apply_target_at_all_raises_so_the_caller_can_skip_the_post(self):
        html = _page(h1="Some Rolling Bursary 2026", body_html="<p>About Someco</p><p>Someco is a company.</p><p>No way to apply is given here.</p>")
        with self.assertRaises(ValueError):
            parse_post("https://vacancyupdate.co.za/some-rolling-bursary", html)

    def test_source_listing_id_is_the_url_slug(self):
        html = _page(
            h1="Vans Job as Sales Assistant 2026",
            body_html=(
                "<p>About Vans</p><p>Vans is a footwear brand.</p>"
                "<p>Apply online at:</p>"
                '<a href="https://vans.example.com/apply">Apply here</a>'
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/vans-sales-assistant", html)
        self.assertEqual(listing.source, "vacancyupdate")
        self.assertEqual(listing.source_listing_id, "vans-sales-assistant")

    def test_learnership_in_title_classifies_as_learnership_type(self):
        html = _page(
            h1="Hollard IT Learnership 2026",
            body_html=(
                "<p>About Hollard</p><p>Hollard is an insurer.</p>"
                "<p>Apply online:</p>"
                '<a href="https://hollard.example.com/apply">Apply here</a>'
            ),
        )
        listing = parse_post("https://vacancyupdate.co.za/hollard-it-learnership", html)
        self.assertEqual(listing.listing_type, ListingType.learnership)


if __name__ == "__main__":
    unittest.main()
