"""Tests for the System One decision gate (no network)."""

import unittest
from unittest import mock

from src.llm.decision_gate import (
    choose_effort,
    decide,
    probability_margin,
    systemone_url,
)


class MarginTest(unittest.TestCase):
    def test_top_two_difference(self):
        self.assertAlmostEqual(
            probability_margin({"a": 0.9, "b": 0.07, "c": 0.03}), 0.83
        )

    def test_single_option_has_no_margin(self):
        self.assertEqual(probability_margin({"a": 1.0}), 0.0)


class ChooseEffortTest(unittest.TestCase):
    def test_trivial_needs_both_conditions(self):
        self.assertEqual(choose_effort("trivial", 0.65, 0.50), "low")
        self.assertIsNone(choose_effort("trivial", 0.649, 0.50))
        self.assertIsNone(choose_effort("trivial", 0.65, 0.499))

    def test_complex_is_more_permissive(self):
        self.assertEqual(choose_effort("complex", 0.60, 0.25), "max")
        self.assertIsNone(choose_effort("complex", 0.59, 0.90))

    def test_normal_and_unknown_are_left_alone(self):
        self.assertIsNone(choose_effort("normal", 0.99, 0.99))
        self.assertIsNone(choose_effort("", 1.0, 1.0))


class EndpointTest(unittest.TestCase):
    def test_appends_protocol_path(self):
        self.assertEqual(
            systemone_url("http://127.0.0.1:8001"), "http://127.0.0.1:8001/v1/systemone"
        )

    def test_keeps_full_path(self):
        url = "http://127.0.0.1:8001/v1/systemone"
        self.assertEqual(systemone_url(url), url)


class DecideTest(unittest.TestCase):
    def _payload(self, choice, confidence, probabilities):
        return {
            "answers": {
                "complexity": {
                    "choice": choice,
                    "confidence": confidence,
                    "probabilities": probabilities,
                }
            }
        }

    def test_maps_complex_to_max(self):
        payload = self._payload(
            "complex", 0.84, {"trivial": 0.004, "normal": 0.10, "complex": 0.896}
        )
        with mock.patch("src.llm.decision_gate.ask", return_value=payload):
            decision = decide("http://127.0.0.1:8001", "設計を見直して")
        self.assertEqual(decision.effort, "max")
        self.assertAlmostEqual(decision.margin, 0.796)

    def test_long_input_never_goes_low(self):
        payload = self._payload(
            "trivial", 0.95, {"trivial": 0.95, "normal": 0.04, "complex": 0.01}
        )
        with mock.patch("src.llm.decision_gate.ask", return_value=payload):
            decision = decide("http://127.0.0.1:8001", "x" * 501)
        self.assertIsNone(decision.effort)

    def test_short_trivial_goes_low(self):
        payload = self._payload(
            "trivial", 0.93, {"trivial": 0.958, "normal": 0.032, "complex": 0.010}
        )
        with mock.patch("src.llm.decision_gate.ask", return_value=payload):
            decision = decide("http://127.0.0.1:8001", "今日の天気は？")
        self.assertEqual(decision.effort, "low")


if __name__ == "__main__":
    unittest.main()
