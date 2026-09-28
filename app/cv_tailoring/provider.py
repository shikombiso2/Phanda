from __future__ import annotations

from typing import Protocol

from app.cv_tailoring.schemas import AnalysisPlan, CandidateFacts, JobRequirements, MatchingStrategy, TailoredCv, ValidationIssue


class TailoringProvider(Protocol):
    name: str
    model_name: str

    async def analyze_and_plan(self, candidate_text: str, job: dict) -> AnalysisPlan: ...

    async def generate(
        self, candidate: CandidateFacts, job: JobRequirements, strategy: MatchingStrategy, listing: dict
    ) -> TailoredCv: ...

    async def revise(
        self,
        candidate: CandidateFacts,
        job: JobRequirements,
        strategy: MatchingStrategy,
        listing: dict,
        draft: TailoredCv,
        issues: list[ValidationIssue],
    ) -> TailoredCv: ...


class ProviderError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False, retry_after_seconds: float | None = None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
