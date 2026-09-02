from __future__ import annotations

import re

from app.cv_tailoring.schemas import AnalysisPlan, CandidateFact, TailoredCv, ValidationIssue

NUMBER_RE = re.compile(r"\b\d+(?:[,.]\d+)?%?\b")
PROPER_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
ORGANIZATION_RE = re.compile(r"\b[A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*\s+(?:Company|Corporation|Corp|Ltd|Limited|Inc|LLC|Pty)\b")
QUALIFICATION_RE = re.compile(r"\b(?:bachelor(?:'s)?|master(?:'s)?|diploma|degree|certificate|certification|matric|nqf)\b", re.IGNORECASE)
TITLE_RE = re.compile(r"\b(?:developer|engineer|manager|analyst|assistant|intern|specialist|coordinator|consultant|administrator|officer|director|lead)\b", re.IGNORECASE)
SKILL_SECTION = "skills"


def validate_analysis(plan: AnalysisPlan, source_text: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for fact in plan.candidate_facts.facts:
        if fact.id in seen:
            issues.append(ValidationIssue(code="duplicate_fact_id", detail=f"Duplicate fact id {fact.id}"))
        seen.add(fact.id)
        for span in fact.source_spans:
            if span.end > len(source_text) or span.start >= span.end:
                issues.append(ValidationIssue(code="invalid_source_span", detail=f"Invalid span for {fact.id}"))
                continue
            actual = " ".join(source_text[span.start : span.end].split())
            if " ".join(span.excerpt.split()) != actual:
                issues.append(ValidationIssue(code="source_excerpt_mismatch", detail=f"Source excerpt mismatch for {fact.id}"))
    return issues


def validate_tailored_cv(draft: TailoredCv, facts: list[CandidateFact], requirement_ids: set[str]) -> list[ValidationIssue]:
    fact_map = {fact.id: fact for fact in facts}
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
            _validate_claim_text(claim.text, evidence, section.name, issues)
    return issues


def _validate_claim_text(text: str, evidence: str, section: str, issues: list[ValidationIssue]) -> None:
    evidence_lower = evidence.lower()
    for number in NUMBER_RE.findall(text):
        if number not in evidence:
            issues.append(ValidationIssue(code="unsupported_metric", detail=f"Unsupported number {number}", section=section))
    for name in PROPER_NAME_RE.findall(text):
        if name.lower() not in evidence_lower and name.lower() not in {"professional summary", "cover letter"}:
            issues.append(ValidationIssue(code="unsupported_named_claim", detail=f"Unsupported named claim {name}", section=section))
    for employer in ORGANIZATION_RE.findall(text):
        if employer.lower() not in evidence_lower:
            issues.append(ValidationIssue(code="unsupported_employer", detail=f"Unsupported employer {employer}", section=section))
    for qualification in QUALIFICATION_RE.findall(text):
        if qualification.lower() not in evidence_lower:
            issues.append(ValidationIssue(code="unsupported_qualification", detail=f"Unsupported qualification {qualification}", section=section))
    for title in TITLE_RE.findall(text):
        if title.lower() not in evidence_lower:
            issues.append(ValidationIssue(code="unsupported_job_title", detail=f"Unsupported job title {title}", section=section))
    if section.lower() == SKILL_SECTION:
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
