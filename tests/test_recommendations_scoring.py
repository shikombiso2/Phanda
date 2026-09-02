import unittest

from app.recommendations.schemas import CompatibilityFactor
from app.recommendations.scoring import combine, score_from_probability


def factor(key: str, probability: float, weight: float = 1.0) -> CompatibilityFactor:
    return CompatibilityFactor(key=key, label=key, probability=probability, weight=weight)


class CombineTests(unittest.TestCase):
    def test_all_neutral_factors_combine_to_neutral(self):
        probability = combine([factor("a", 0.5), factor("b", 0.5), factor("c", 0.5)])
        self.assertAlmostEqual(probability, 0.5, places=6)

    def test_all_strong_factors_combine_to_a_high_score(self):
        probability = combine([factor("a", 0.9), factor("b", 0.9), factor("c", 0.9)])
        self.assertGreater(probability, 0.85)

    def test_all_weak_factors_combine_to_a_low_score(self):
        probability = combine([factor("a", 0.1), factor("b", 0.1)])
        self.assertLess(probability, 0.15)

    def test_higher_weight_factor_dominates_the_combination(self):
        dominant_high = combine([factor("skills", 0.95, weight=3.0), factor("salary", 0.1, weight=0.5)])
        dominant_low = combine([factor("skills", 0.1, weight=3.0), factor("salary", 0.95, weight=0.5)])
        self.assertGreater(dominant_high, 0.7)
        self.assertLess(dominant_low, 0.3)

    def test_no_factors_returns_neutral(self):
        self.assertEqual(combine([]), 0.5)

    def test_including_a_neutral_factor_dilutes_confidence_versus_omitting_it(self):
        """A weighted average of "90% confident" and "50%/neutral" is,
        correctly, less confident than "90%" alone -- adding a genuinely
        uninformative opinion to a pool should reduce net certainty. This is
        exactly why a cold-start user's missing engagement history is
        *omitted* from the factor list in recommendations/service.py rather
        than appended at a neutral 0.5: appending it would needlessly dilute
        every new user's score for having no history yet, which is not
        evidence of a worse fit."""
        undiluted = combine([factor("skills", 0.9, weight=3.0)])
        diluted = combine([factor("skills", 0.9, weight=3.0), factor("engagement", 0.5, weight=0.75)])
        self.assertGreater(undiluted, diluted)


class ScoreFromProbabilityTests(unittest.TestCase):
    def test_maps_to_a_0_to_100_integer(self):
        self.assertEqual(score_from_probability(0.5), 50)
        self.assertEqual(score_from_probability(0.874), 87)
        self.assertEqual(score_from_probability(0.0), 0)
        self.assertEqual(score_from_probability(1.0), 100)


if __name__ == "__main__":
    unittest.main()
