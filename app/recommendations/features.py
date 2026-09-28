"""Content-based compatibility features for one (candidate, listing) pair.

Every function here is pure -- no database access, no randomness -- so the
whole scoring pipeline is unit-testable with plain Python values and
reproducible for the same inputs. Each returns a probability in [0, 1]: "how
likely is this factor, on its own, to indicate a good fit" -- not a learned
probability (there is no outcome data yet to learn one from; see
docs/RECOMMENDATIONS.md), but a hand-calibrated estimate that is honest about
being a starting prior rather than a fitted model.

The one rule every factor follows: missing data means "no evidence", which
maps to 0.5 (neutral), never to 0 (bad) or a skipped/zeroed contribution.
Punishing a listing or a profile for a field nobody filled in is exactly the
kind of silent unfairness a probabilistic framing is supposed to avoid.
"""

from __future__ import annotations

import re

from app.core.models import ExperienceLevel, JobType, ListingType

NEUTRAL = 0.5

# --- skills ----------------------------------------------------------------


def normalize_skill(value: str) -> str:
    return value.strip().lower()


def skill_compatibility(
    profile_skills: list[str], cv_skills: list[str], required_skills: list[str]
) -> tuple[float, list[str], list[str]]:
    """Returns (probability, matched, missing).

    profile_skills and cv_skills are two independent sources -- the user's
    own typed-in skills, and whatever extract_required_skills() found in
    their active CV's text (see CvVersion.extracted_skills) -- unioned here
    into one "owned" set. Never merged into Profile.skills itself: that
    column stays exactly what the user explicitly stated, since PUT
    /profile fully replaces it on every save (app/profiles/router.py) and a
    machine-written skill sitting in that column would be silently deleted
    by an unrelated edit. matched/missing below report the unioned result
    only -- callers don't need to know which source a match came from.

    A listing tagged with no required skills at all is neutral (0.5), not
    automatically 0 -- the old implementation's behaviour, which unfairly
    buried every under-tagged listing at the bottom of the feed regardless
    of actual fit. That neutral-for-empty case is the ONE thing preserved
    unconditionally here.

    For a listing that does state required skills, the score is the plain
    matched/required proportion -- matched_count / max(1, len(required)) --
    not the Laplace-smoothed (matched + 1) / (required + 2) this used to be.
    The smoothed version actively mis-ranked listings: it made a listing
    needing 1 skill the candidate has (1/1, "genuinely 100% covered") score
    IDENTICAL to one needing 4 skills where only 3 are matched (3/4 -- (3+1)/
    (4+2) = 4/6 = (1+1)/(1+2) exactly), and WORSE than a listing needing 6
    skills where 4 are matched ((4+1)/(6+2) = 5/8 = 0.625 < 2/3), even though
    matching four distinct required skills is stronger real evidence of fit
    than matching one. A plain proportion doesn't have that failure: it's
    monotonic in both matched count and coverage, so "matched everything
    required" always outscores "matched some of several", and "matched more
    of several" always outscores "matched fewer of several", regardless of
    the sizes involved.

    One more neutral case, distinct from the empty-required one above: a
    candidate who hasn't stated ANY skills at all (empty profile.skills AND
    no CV skills) is a true cold start, not a confirmed non-match -- per
    this module's own rule, missing data is "no evidence" (0.5), never "bad"
    (0.0). A plain proportion can't tell "stated some skills, none of which
    overlap" (a real signal: 0.0 is correct) apart from "stated nothing at
    all" (no signal either way) on its own, so that case is handled
    explicitly here rather than folded into the division.
    """
    required = sorted({normalize_skill(skill) for skill in required_skills if skill.strip()})
    owned = {normalize_skill(skill) for skill in [*profile_skills, *cv_skills] if skill.strip()}
    if not required:
        return NEUTRAL, [], []
    matched = [skill for skill in required if skill in owned]
    missing = [skill for skill in required if skill not in owned]
    probability = NEUTRAL if not owned else len(matched) / max(1, len(required))
    return probability, matched, missing


# --- experience --------------------------------------------------------

_SENIOR_RE = re.compile(r"\b(senior|lead|head of|principal|manager|supervisor)\b", re.IGNORECASE)
_ENTRY_RE = re.compile(r"\b(junior|graduate|entry[- ]level|intern|internship|trainee|learnership)\b", re.IGNORECASE)

_EXPERIENCE_ORDINAL = {ExperienceLevel.none: 0, ExperienceLevel.some: 1, ExperienceLevel.experienced: 2}


def infer_listing_seniority(title: str, description: str) -> int | None:
    """0 = entry-level, 1 = mid/unspecified-but-signalled, 2 = senior.
    None means no seniority signal was found at all -- most entry-level
    retail/admin postings say neither "junior" nor "senior"."""
    haystack = f"{title} {description}"
    if _SENIOR_RE.search(haystack):
        return 2
    if _ENTRY_RE.search(haystack):
        return 0
    return None


def experience_compatibility(profile_experience: ExperienceLevel, title: str, description: str) -> tuple[float, int | None]:
    listing_seniority = infer_listing_seniority(title, description)
    if listing_seniority is None:
        return NEUTRAL, None
    distance = abs(_EXPERIENCE_ORDINAL[profile_experience] - listing_seniority)
    probability = {0: 0.85, 1: 0.55, 2: 0.2}[distance]
    return probability, listing_seniority


# --- job type ----------------------------------------------------------

_TRAINING_TYPES = {ListingType.internship, ListingType.learnership, ListingType.apprenticeship, ListingType.bursary}

_JOB_TYPE_COMPATIBILITY: dict[JobType, dict[ListingType, float]] = {
    JobType.any: {t: 0.7 for t in ListingType},
    JobType.full_time: {ListingType.job: 0.85, **{t: 0.4 for t in _TRAINING_TYPES}},
    JobType.part_time: {ListingType.job: 0.8, **{t: 0.45 for t in _TRAINING_TYPES}},
    JobType.internship: {ListingType.internship: 0.9, ListingType.job: 0.3, **{t: 0.6 for t in _TRAINING_TYPES - {ListingType.internship}}},
    JobType.learnership: {ListingType.learnership: 0.9, ListingType.job: 0.3, **{t: 0.6 for t in _TRAINING_TYPES - {ListingType.learnership}}},
}


def job_type_compatibility(profile_job_type: JobType, listing_type: ListingType) -> float:
    return _JOB_TYPE_COMPATIBILITY[profile_job_type].get(listing_type, NEUTRAL)


# --- location ------------------------------------------------------------


def _normalize_place(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def location_compatibility(profile_location: str | None, open_to_remote: bool, listing_location: str | None) -> float:
    listing_is_remote = bool(listing_location) and "remote" in listing_location.lower()
    if open_to_remote and listing_is_remote:
        return 0.9
    if not profile_location or not listing_location:
        return NEUTRAL
    a, b = _normalize_place(profile_location), _normalize_place(listing_location)
    if a and b and (a == b or a in b or b in a):
        return 0.85
    if open_to_remote:
        # Open to remote broadens acceptable locations even without an exact
        # match -- still worth seeing, just not a confirmed local match.
        return 0.5
    return 0.3


# --- industry / category ------------------------------------------------


def industry_compatibility(profile_industries: list[str], listing_category: str | None) -> float:
    if not listing_category or not profile_industries:
        return NEUTRAL
    category = listing_category.lower()
    for industry in profile_industries:
        normalized = industry.strip().lower()
        if normalized and (normalized in category or category in normalized):
            return 0.8
    return 0.35


# --- salary --------------------------------------------------------------


def salary_compatibility(
    profile_min: int | None, profile_max: int | None, listing_min: int | None, listing_max: int | None
) -> float:
    if profile_min is None and profile_max is None:
        return NEUTRAL
    if listing_min is None and listing_max is None:
        return NEUTRAL
    if profile_min is not None and listing_max is not None and listing_max < profile_min:
        return 0.3  # the listing pays less than the candidate wants
    return 0.8  # ranges overlap, or the listing pays at/above what was asked


# --- engagement (light use of saved/applied/tailored history) ----------


def engagement_compatibility(required_skills: list[str], engaged_skills: set[str]) -> tuple[float, bool]:
    """Returns (probability, was_applicable). `was_applicable` is False for a
    user with no saved/applied/tailored history at all -- true cold start --
    in which case the caller omits this factor entirely rather than scoring
    it, since there is no evidence one way or the other, and a fixed neutral
    0.5 injected into the combination would just be dead weight, not signal.
    """
    if not engaged_skills:
        return NEUTRAL, False
    required = {normalize_skill(skill) for skill in required_skills if skill.strip()}
    if not required:
        return NEUTRAL, False
    overlap = len(required & engaged_skills) / len(required)
    return (0.5 + overlap * 0.4), True
