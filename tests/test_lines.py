"""Tests for the stateless line runner."""

import tempfile
import unittest
from pathlib import Path

from src.pipeline.lines import LINES, line_done, line_ready, natural_key, plan

ROOT = Path(__file__).resolve().parent.parent / "samples" / "lessons"


class NaturalKeyTest(unittest.TestCase):
    def test_numeric_order_not_lexical(self):
        ids = ["V3-X-C01-S01-L10", "V3-X-C01-S01-L02", "V3-X-C01-S01-L01"]
        self.assertEqual(sorted(ids, key=natural_key),
                         ["V3-X-C01-S01-L01", "V3-X-C01-S01-L02", "V3-X-C01-S01-L10"])


class PlanTest(unittest.TestCase):
    def test_line2_skips_finished_lessons(self):
        pending = plan(ROOT, "line2")
        self.assertEqual([p["lesson"] for p in pending],
                         ["V3-DEMO-CIV-C01-S01-L02"])

    def test_force_includes_finished_lessons(self):
        pending = plan(ROOT, "line2", force=True)
        self.assertEqual(len(pending), 3)

    def test_limit_is_respected(self):
        self.assertEqual(len(plan(ROOT, "line2", force=True, limit=1)), 1)

    def test_line4_requires_script(self):
        # 4-point lessons are ready for video; the finished one is included by --force
        self.assertEqual([p["lesson"] for p in plan(ROOT, "line4", force=True)],
                         ["V3-DEMO-CIV-C01-S01-L01", "V3-DEMO-M1-C01-S01-L10"])
        # without --force, only the one that is not yet produced remains
        self.assertEqual([p["lesson"] for p in plan(ROOT, "line4")],
                         ["V3-DEMO-CIV-C01-S01-L01"])

    def test_line1_finds_unprocessed_lessons(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "SUBJ" / "V3-EMPTY-C01-S01-L01"
            empty.mkdir(parents=True)
            (empty / "note.txt").write_text("x", encoding="utf-8")
            self.assertEqual(len(plan(Path(tmp), "line1")), 1)


class DoneReadyTest(unittest.TestCase):
    def test_done_requires_every_output(self):
        lesson = ROOT / "V3-DEMO-CIV" / "V3-DEMO-CIV-C01-S01-L01"
        self.assertTrue(line_done(lesson, LINES["line2"]))
        self.assertFalse(line_done(lesson, LINES["line4"]))

    def test_ready_requires_upstream_input(self):
        lesson = ROOT / "V3-DEMO-CIV" / "V3-DEMO-CIV-C01-S01-L02"
        self.assertTrue(line_ready(lesson, LINES["line2"]))
        self.assertFalse(line_ready(lesson, LINES["line4"]))

    def test_line1_has_no_prerequisites(self):
        lesson = ROOT / "V3-DEMO-CIV" / "V3-DEMO-CIV-C01-S01-L02"
        self.assertTrue(line_ready(lesson, LINES["line1"]))


if __name__ == "__main__":
    unittest.main()
