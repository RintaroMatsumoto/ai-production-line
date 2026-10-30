"""Tests for the visual layout gate."""

import unittest

from src.pipeline.gates.visual_layout import evaluate, union_bbox


def layout(boxes, w=1920, h=1080):
    return {
        "canvas": {"w": w, "h": h},
        "elements": [{"id": f"e{i}", "bbox": list(b)} for i, b in enumerate(boxes)],
    }


class UnionBBoxTest(unittest.TestCase):
    def test_union_covers_all(self):
        self.assertEqual(union_bbox([[10, 20, 100, 50], [0, 0, 10, 10]]),
                         [0, 0, 110, 70])


class EvaluateTest(unittest.TestCase):
    def test_centered_passes(self):
        result = evaluate(layout([[760, 440, 400, 200]]))
        self.assertTrue(result["ok"], result["problems"])
        self.assertAlmostEqual(result["offset"]["dx"], 0, places=1)

    def test_overflow_fails(self):
        result = evaluate(layout([[1800, 440, 400, 200]]))
        self.assertFalse(result["ok"])
        self.assertTrue(result["overflow"])
        self.assertTrue(any("overflows" in p for p in result["problems"]))

    def test_off_center_fails(self):
        result = evaluate(layout([[100, 440, 400, 200]]), tolerance=12)
        self.assertFalse(result["ok"])
        self.assertTrue(any("off-center" in p for p in result["problems"]))

    def test_tolerance_is_configurable(self):
        result = evaluate(layout([[540, 440, 400, 200]]), tolerance=2000)
        self.assertTrue(result["ok"], result["problems"])

    def test_empty_scene_fails(self):
        result = evaluate({"canvas": {"w": 1920, "h": 1080}, "elements": []})
        self.assertFalse(result["ok"])

    def test_invalid_canvas_fails(self):
        result = evaluate({"canvas": {"w": 0, "h": 0}, "elements": []})
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
