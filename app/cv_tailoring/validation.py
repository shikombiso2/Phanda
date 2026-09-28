from __future__ import annotations

import re

from app.cv_tailoring.schemas import AnalysisPlan, CandidateFact, JobRequirement, TailoredCv, ValidationIssue

NUMBER_RE = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")
PROPER_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
ORGANIZATION_RE = re.compile(r"\b[A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*\s+(?:Company|Corporation|Corp|Ltd|Limited|Inc|LLC|Pty)\b")
QUALIFICATION_RE = re.compile(r"\b(?:bachelor(?:'s)?|master(?:'s)?|diploma|degree|certificate|certification|matric|nqf)\b", re.IGNORECASE)
TITLE_RE = re.compile(r"\b(?:developer|engineer|manager|analyst|assistant|intern|specialist|coordinator|consultant|administrator|officer|director|lead)\b", re.IGNORECASE)
SKILL_SECTION = "skills"


def validate_analysis(plan: AnalysisPlan, source_text: str) -> list[ValidationIssue]:
    """Ground every candidate fact's source_spans in source_text by search,
    not by trusting Gemini's character offsets.

    LLMs cannot count characters reliably: offsets drift further from correct
    the more text precedes them, even when the quoted excerpt itself is a
    verbatim, unfabricated match. Locating each excerpt with a substring
    search (after whitespace/case normalisation) and overwriting start/end
    with the true offsets keeps the fabrication check -- an excerpt not
    present anywhere in the source is still rejected -- while dropping the
    offset arithmetic the model cannot be relied on to produce.
    """
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    normalized_source = " ".join(source_text.split()).lower()
    for fact in plan.candidate_facts.facts:
        if fact.id in seen:
            issues.append(ValidationIssue(code="duplicate_fact_id", detail=f"Duplicate fact id {fact.id}"))
        seen.add(fact.id)
        for span in fact.source_spans:
            normalized_excerpt = " ".join(span.excerpt.split()).lower()
            if not normalized_excerpt:
                issues.append(ValidationIssue(code="invalid_source_span", detail=f"Empty excerpt for {fact.id}"))
                continue
            position = normalized_source.find(normalized_excerpt)
            if position == -1:
                issues.append(ValidationIssue(code="source_excerpt_mismatch", detail=f"Source excerpt mismatch for {fact.id}"))
                continue
            span.start = position
            span.end = position + len(normalized_excerpt)
    issues.extend(_completeness_issues(plan, source_text))
    return issues


# CV text extraction (app/cv_tailoring/extraction.py's _usable_text) collapses
# every run of whitespace -- including every newline -- into a single space
# before this ever runs, so there is no line-break structure left to split
# on. This is the closest cheap proxy available: in ordinary resume text, one
# bullet/list item ending (a lowercase letter, digit, or closing parenthesis)
# is followed by the next item starting with a capital letter, with nothing
# but a single collapsed space between them -- which is exactly what used to
# be a newline or bullet marker before collapsing. It also fires inside an
# ordinary multi-clause sentence that happens to contain a capitalised word
# (a product name, an acronym) after a lowercase word, which means this
# OVER-estimates the true item count in prose-heavy text. That is the safe
# direction for a completeness floor: it makes the check slightly more
# willing to ask for a retry, never more willing to wave through a
# genuinely under-extracted plan. This is deliberately not exact --
# confirmed sufficient to catch the real case (5 achievement bullets
# collapsed into a single job-header fact, 2 of 6 skills never extracted at
# all) without needing real NLP.
_ITEM_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9\)\.])\s(?=[A-Z])")
_SECTION_MARKERS = ["WORK EXPERIENCE", "EXPERIENCE", "EDUCATION", "SKILLS", "REFERENCES", "PROFILE"]
_MIN_ITEMS_TO_CHECK = 3
_MIN_SHORTFALL_TO_FLAG = 3  # at least this many items missing, not a ratio -- see _completeness_issues.
# Set above the observed noise floor of the boundary heuristic itself: a
# two-word capitalised skill/product name ("Microsoft Excel", "Microsoft
# Word") reads as two items to _ITEM_BOUNDARY_RE, not one, so a fully,
# correctly extracted real CV can still show an estimated count 1-2 higher
# than its true item count. 3 stays well clear of that self-inflicted noise
# while still catching the confirmed real shortfalls (2 of 6 skills, all 5
# of 5 bullets under a role).


def _estimate_item_count(segment: str) -> int:
    segment = segment.strip()
    if not segment:
        return 0
    return len(_ITEM_BOUNDARY_RE.split(segment))


def _next_section_offset(source_text: str, after: int) -> int:
    end = len(source_text)
    for marker in _SECTION_MARKERS:
        match = re.search(rf"\b{re.escape(marker)}\b", source_text[after:], re.IGNORECASE)
        if match:
            end = min(end, after + match.start())
    return end


def _completeness_issues(plan: AnalysisPlan, source_text: str) -> list[ValidationIssue]:
    """A rough sanity floor, not a precise classifier: does the plan contain
    at least roughly as many skill/achievement facts as the source text
    plainly seems to list? Confirmed live: real content (2 of 6 listed
    skills, every achievement bullet under both jobs) can be silently
    under-extracted with nothing in the pipeline ever noticing -- every fact
    that WAS produced still passes the fabrication check above, because it
    really is grounded; there was just no requirement that there be enough
    of them. Flagged on an absolute shortfall (missing at least
    _MIN_SHORTFALL_TO_FLAG items), not a ratio -- the confirmed real case
    was 2 of 6 skills missing (a third short, not half), so a "less than
    half captured" ratio would have missed exactly the bug this exists to
    catch.
    """
    issues: list[ValidationIssue] = []
    facts = plan.candidate_facts.facts

    skills_match = re.search(r"\bSKILLS\b", source_text, re.IGNORECASE)
    if skills_match:
        start = skills_match.end()
        end = _next_section_offset(source_text, start)
        estimated = _estimate_item_count(source_text[start:end])
        skill_fact_count = sum(1 for f in facts if f.category == "skill")
        if estimated >= _MIN_ITEMS_TO_CHECK and estimated - skill_fact_count >= _MIN_SHORTFALL_TO_FLAG:
            issues.append(
                ValidationIssue(
                    code="incomplete_skill_extraction",
                    detail=f"Source text lists an estimated ~{estimated} skills but only {skill_fact_count} skill facts were extracted",
                )
            )

    experience_facts = [f for f in facts if f.category == "experience"]
    ordered = sorted(experience_facts, key=lambda f: min(span.start for span in f.source_spans))
    for i, header_fact in enumerate(ordered):
        block_start = max(span.end for span in header_fact.source_spans)
        block_end = (
            min(span.start for span in ordered[i + 1].source_spans)
            if i + 1 < len(ordered)
            else _next_section_offset(source_text, block_start)
        )
        if block_end <= block_start:
            continue
        estimated = _estimate_item_count(source_text[block_start:block_end])
        bullet_fact_count = sum(
            1 for f in experience_facts if any(block_start <= span.start < block_end for span in f.source_spans)
        )
        if estimated >= _MIN_ITEMS_TO_CHECK and estimated - bullet_fact_count >= _MIN_SHORTFALL_TO_FLAG:
            issues.append(
                ValidationIssue(
                    code="incomplete_experience_extraction",
                    detail=(
                        f"Source text lists an estimated ~{estimated} achievement lines under this role "
                        f"but only {bullet_fact_count} were extracted as separate facts"
                    ),
                )
            )
    return issues


def validate_tailored_cv(
    draft: TailoredCv, facts: list[CandidateFact], requirements: list[JobRequirement]
) -> list[ValidationIssue]:
    fact_map = {fact.id: fact for fact in facts}
    requirement_ids = {requirement.id for requirement in requirements}
    # The job listing's own wording is real, grounded text too -- it just
    # belongs to the employer instead of the candidate. Tailoring a claim
    # MEANS echoing that wording, so a phrase lifted from the listing is not
    # an invention and must not be scored as one. Passed to
    # _validate_claim_text as a second evidence pool, which deliberately
    # accepts it for some checks and not others -- see there.
    job_evidence = " ".join(requirement.text for requirement in requirements)
    issues: list[ValidationIssue] = []
    sections = {section.name.lower() for section in draft.sections}
    if "professional summary" not in sections or "skills" not in sections:
        issues.append(ValidationIssue(code="missing_required_sections", detail="Professional Summary and Skills are required"))

    for section in [*draft.sections, type("CoverLetter", (), {"name": "Cover Letter", "claims": draft.cover_letter})()]:
        for claim in section.claims:
            referenced = [fact_map.get(identifier) for identifier in claim.source_fact_ids]
            if not referenced or any(fact is None for fact in referenced):
                issues.append(ValidationIssue(code="unknown_fact_id", detail="A claim references an unknown candidate fact", section=section.name))
                continue
            if unknown := set(claim.job_requirement_ids) - requirement_ids:
                issues.append(ValidationIssue(code="unknown_job_requirement", detail=f"Unknown requirements: {sorted(unknown)}", section=section.name))
            evidence = " ".join(
                " ".join(span.excerpt for span in fact.source_spans) for fact in referenced if fact is not None
            )
            _validate_claim_text(claim.text, evidence, job_evidence, section.name, issues)
    return issues


def _validate_claim_text(text: str, evidence: str, job_evidence: str, section: str, issues: list[ValidationIssue]) -> None:
    """Two evidence pools, and which checks may draw on which is the whole
    point of this function.

    `evidence` is the candidate's own source text. `job_evidence` is the
    listing's requirement text. NAMING checks (proper names, employers, job
    titles) accept either: echoing the employer's own terminology back at
    them is what tailoring IS, and flagging it as fabrication forced a
    pointless correction round on every genuinely tailored draft.

    METRICS and QUALIFICATIONS deliberately stay candidate-only. A number or
    a qualification is a claim about what this person has done or earned,
    and the job listing saying the words "diploma" or "12" is not evidence
    that she holds one -- widening those two would let the listing's own
    wishlist authorise claiming a qualification she does not have, which is
    the single most consequential lie a CV can carry.
    """
    evidence_lower = evidence.lower()
    nameable_lower = f"{evidence} {job_evidence}".lower()
    for number in NUMBER_RE.findall(text):
        if number not in evidence:
            issues.append(ValidationIssue(code="unsupported_metric", detail=f"Unsupported number {number}", section=section))
    for name in PROPER_NAME_RE.findall(text):
        if name.lower() not in nameable_lower and name.lower() not in {"professional summary", "cover letter"}:
            issues.append(ValidationIssue(code="unsupported_named_claim", detail=f"Unsupported named claim {name}", section=section))
    for employer in ORGANIZATION_RE.findall(text):
        if employer.lower() not in nameable_lower:
            issues.append(ValidationIssue(code="unsupported_employer", detail=f"Unsupported employer {employer}", section=section))
    for qualification in QUALIFICATION_RE.findall(text):
        if qualification.lower() not in evidence_lower:
            issues.append(ValidationIssue(code="unsupported_qualification", detail=f"Unsupported qualification {qualification}", section=section))
    for title in TITLE_RE.findall(text):
        if title.lower() not in nameable_lower:
            issues.append(ValidationIssue(code="unsupported_job_title", detail=f"Unsupported job title {title}", section=section))
    if section.lower() == SKILL_SECTION:
        # Candidate evidence only, unchanged and intentionally strict: a
        # Skills entry is a flat factual assertion, not narrative framing.
        _validate_skill_claim(text, evidence_lower, section, issues)


def _validate_skill_claim(text: str, evidence_lower: str, section: str, issues: list[ValidationIssue]) -> None:
    """Skills sections must name only skills present in their cited source facts.

    We intentionally do not apply this strict word-level check to narrative
    sections: ordinary connecting language ("worked", "experience") should
    not need to appear verbatim in a source span.
    """
    candidates = [part.strip(" .-•") for part in re.split(r"[,;|\n]", text) if part.strip(" .-•")]
    for candidate in candidates:
        normalized = candidate.lower()
        if normalized not in evidence_lower:
            issues.append(ValidationIssue(code="unsupported_skill", detail=f"Unsupported skill {candidate}", section=section))
