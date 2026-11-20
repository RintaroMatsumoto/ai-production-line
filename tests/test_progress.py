"""Tests for progress computed from file existence."""

import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.lines import progress

ROOT = Path(__file__).resolve().parent.parent / "samples" / "lessons"


class ProgressTest(unittest.TestCase):
    def test_sample_fixture_counts(self):
        result = progress(ROOT)
        self.assertEqual(result["lessons"], 3)
        self.assertEqual(result["counts"], {
            "pack": 3, "text": 2, "test": 2, "script": 2, "video": 1, "youtube": 1,
        })

    def test_average_is_over_six_stages(self):
        result = progress(ROOT)
        # (3+2+2+2+1+1) / (6*3) * 100 = 61.1
        self.assertAlmostEqual(result["average_percent"], 61.1, places=1)

    def test_empty_root_is_zero_not_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = progress(Path(tmp))
            self.assertEqual(result["lessons"], 0)
            self.assertEqual(result["average_percent"], 0.0)

    def test_youtube_requires_an_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "S" / "V3-T-C01-S01-L01"
            lesson.mkdir(parents=True)
            for name in ("pack.json", "text.json", "test.json", "script.md",
                         "video.mp4"):
                (lesson / name).write_text("{}", encoding="utf-8")
            (lesson / "status.json").write_text(
                json.dumps({"line4": {}}), encoding="utf-8")
            result = progress(Path(tmp))
            self.assertEqual(result["counts"]["video"], 1)
            self.assertEqual(result["counts"]["youtube"], 0)

    def test_broken_status_json_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp) / "S" / "V3-T-C01-S01-L01"
            lesson.mkdir(parents=True)
            (lesson / "pack.json").write_text("{}", encoding="utf-8")
            (lesson / "status.json").write_text("{not json", encoding="utf-8")
            result = progress(Path(tmp))
            self.assertEqual(result["counts"]["youtube"], 0)


if __name__ == "__main__":
    unittest.main()
