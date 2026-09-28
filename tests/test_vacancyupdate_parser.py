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


# Reproduces the real Aramex Learnership page's structure exactly: ad wrapper
# divs carrying adsbygoogle <script>/<ins>, the post-shortlink "Copy URL"
# widget with its own inline onclick <script>, section headings as a <strong>
# opening its own <p> (the site never uses <h2>/<h3>), and eligibility
# criteria as genuine <ul>/<ol><li> markup.
_ARAMEX_BODY = """
<div class="stream-item stream-item-above-post-content"><div class="stream-item-size">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-64773"></script>
<ins class="adsbygoogle" style="display:block" data-ad-slot="2237923639"></ins>
<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
</div></div>
<p><strong>About Aramex</strong><br /> Aramex is a global logistics and transportation company.</p>
<p><strong>About the Aramex Learnership 2026</strong><br /> Aramex is searching for candidates.</p>
<p><strong>Eligibility Criteria</strong><br /> Review the requirements before applying.</p>
<p><strong>1. Basic Qualifications</strong></p>
<ul>
<li>Hold a Matric (Grade 12) qualification as the minimum educational requirement</li>
<li>Achieve a minimum pass mark of 45% in all language subjects</li>
<li>Maintain a clear criminal record to qualify for the learnership</li>
</ul>
<p><strong>Application Instructions</strong><br /> Apply online: <a href="https://careers.aramex.com/job/Learner/8496-en_US">Aramex Learnership 2026</a></p>
<ol>
<li>Use Google Chrome to access the application website</li>
<li>Complete the application form carefully</li>
</ol>
<p><strong>Closing Date</strong></p>
<p>Application is available as long as it is not deleted.</p>
<div class="stream-item stream-item-below-post-content">
<ins class="adsbygoogle" data-ad-slot="3319135627"></ins>
<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
</div>
<div class="post-shortlink">
<input type="text" id="short-post-url" value="vacancyupdate.co.za/?p=10224" data-url="https://vacancyupdate.co.za/?p=10224">
<button type="button" id="copy-post-url" class="button">Copy URL</button>
<span id="copy-post-url-msg" style="display:none;">URL Copied</span>
</div>
<script>
document.getElementById('copy-post-url').onclick = function(){
    var copyText = document.getElementById('short-post-url');
    copyText.select();
    navigator.clipboard.writeText(copyText.getAttribute('data-url'));
}
</script>
"""


class VacancyUpdateContentQualityTests(unittest.TestCase):
    """Real listings used to store ad/script junk and the whole post as one
    unbroken run of text. Both are structural, both are covered here."""

    def setUp(self):
        html = _page(h1="Aramex Learnership 2026: Welcoming Unemployed Individuals", body_html=_ARAMEX_BODY)
        self.listing = parse_post("https://vacancyupdate.co.za/aramex-learnership", html)

    def test_ad_and_widget_script_junk_is_excluded(self):
        for junk in [
            "adsbygoogle",
            "getElementById",
            "copyText",
            "navigator.clipboard",
            "Copy URL",
            "URL Copied",
            "pagead2.googlesyndication.com",
        ]:
            self.assertNotIn(junk, self.listing.description, f"{junk!r} leaked into the stored description")

    def test_section_headings_are_preserved_as_markdown_headers(self):
        for heading in [
            "## About Aramex",
            "## About the Aramex Learnership 2026",
            "## Eligibility Criteria",
            "## Application Instructions",
            "## Closing Date",
        ]:
            self.assertIn(heading, self.listing.description)

    def test_eligibility_criteria_stay_list_items_not_run_on_prose(self):
        lines = self.listing.description.splitlines()
        self.assertIn("- Hold a Matric (Grade 12) qualification as the minimum educational requirement", lines)
        self.assertIn("- Achieve a minimum pass mark of 45% in all language subjects", lines)
        self.assertIn("- Maintain a clear criminal record to qualify for the learnership", lines)

    def test_ordered_lists_keep_their_numbering(self):
        lines = self.listing.description.splitlines()
        self.assertIn("1. Use Google Chrome to access the application website", lines)
        self.assertIn("2. Complete the application form carefully", lines)

    def test_paragraphs_are_separated_rather_than_run_together(self):
        self.assertIn(
            "## About Aramex\n\nAramex is a global logistics and transportation company.",
            self.listing.description,
        )

    def test_structural_parsing_still_works_with_junk_removed(self):
        # Removing whole DOM subtrees must not disturb the text-node indices
        # the apply-link lookup walks, nor the company/heading regexes.
        self.assertEqual(self.listing.apply_method, ApplyMethod.ats_link)
        self.assertEqual(self.listing.apply_target, "https://careers.aramex.com/job/Learner/8496-en_US")
        self.assertEqual(self.listing.company, "Aramex")

    def test_skill_extraction_still_works_against_markdown(self):
        # "## " and "- " prefixes must not interfere with the word-boundary
        # keyword matching extract_required_skills does.
        self.assertIn("matric", self.listing.required_skills)


if __name__ == "__main__":
    unittest.main()
