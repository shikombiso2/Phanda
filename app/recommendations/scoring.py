"""Combine independent compatibility factors into one suitability score.

The formulation, directly: each factor is treated as an independent piece of
probabilistic evidence about "is this candidate suitable for this job" --
the same conditional-independence assumption a naive Bayes classifier makes.
Factors are combined by averaging their log-odds (logits), weighted by how
much each factor should count, then mapping back through a sigmoid to get a
single P(suitable). This is a logarithmic opinion pool -- the standard way
to fuse several probabilistic estimates into one -- and it is mathematically
identical to naive-Bayes combination up to the normalizing constant.

What makes this "hand-calibrated" rather than "trained": the weights and the
per-factor probability curves in features.py are set by hand, not fit to
data, because there is no outcome data yet (no signal for "this
recommendation led to a hire" exists anywhere in this product). See
docs/RECOMMENDATIONS.md for the upgrade path once real interaction data
accumulates: the factor structure here does not need to change, only these
numbers move from hand-set priors to fitted weights (e.g. via logistic
regression against saved/applied outcomes).
"""

from __future__ import annotations

import math

from app.recommendations.schemas import CompatibilityFactor

# Hand-set relative importance. Skills is the direct requirement match, so it
# dominates; industry and salary are the least reliable inputs available
# today (industry is a coarse label match, salary is frequently missing), so
# they count least.
FACTOR_WEIGHTS: dict[str, float] = {
    "skills": 3.0,
    "experience": 1.5,
    "job_type": 1.0,
    "location": 1.0,
    "industry": 0.5,
    "salary": 0.5,
    "engagement": 0.75,
}

_EPSILON = 0.02  # keeps logit() finite; a factor is never treated as absolutely certain
NEUTRAL_SCORE_PROBABILITY = 0.5


def _clamp(probability: float) -> float:
    return min(1 - _EPSILON, max(_EPSILON, probability))


def _logit(probability: float) -> float:
    p = _clamp(probability)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def combine(factors: list[CompatibilityFactor]) -> float:
    """Weighted log-odds pool -> a single probability in [0, 1].

    Normalizing by the total weight *actually present* (not a fixed total)
    is what lets a factor be omitted for a cold-start user (see
    features.engagement_compatibility) without mechanically dragging the
    score toward neutral just because fewer terms were summed.
    """
    if not factors:
        return NEUTRAL_SCORE_PROBABILITY
    total_weight = sum(factor.weight for factor in factors)
    if total_weight == 0:
        return NEUTRAL_SCORE_PROBABILITY
    pooled_logit = sum(factor.weight * _logit(factor.probability) for factor in factors) / total_weight
    return _sigmoid(pooled_logit)


def score_from_probability(probability: float) -> int:
    return round(probability * 100)
