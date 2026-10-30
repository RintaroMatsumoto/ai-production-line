"""Tests for the frame distribution planner."""

import unittest

from src.pipeline.distribute import parse_weights, plan, snap, validate


class ParseWeightsTest(unittest.TestCase):
    def test_normalises_to_one(self):
        w = parse_weights("a=1,b=3")
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w["b"], 0.75)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            parse_weights("a")
        with self.assertRaises(ValueError):
            parse_weights("a=0")
        with self.assertRaises(ValueError):
            parse_weights("")

    def test_negative_weight_rejected(self):
        with self.assertRaises(ValueError):
            parse_weights("a=-1")


class SnapTest(unittest.TestCase):
    def test_picks_nearest_scene_start(self):
        starts = [0, 900, 1800, 2700]
        self.assertEqual(snap(starts, 1750, 0, 2700), 1800)
        self.assertEqual(snap(starts, 950, 0, 2700), 900)

    def test_respects_window(self):
        starts = [0, 900, 1800]
        # 1800 is outside [0, 1000], so the nearest in-window start (900) wins.
        self.assertEqual(snap(starts, 1800, 0, 1000), 900)

    def test_clamps_when_window_has_no_candidate(self):
        self.assertEqual(snap([0, 900, 1800], 1800, 1000, 1500), 1500)

    def test_falls_back_when_no_candidate(self):
        self.assertEqual(snap([], 500, 0, 1000), 500)


class PlanTest(unittest.TestCase):
    def test_single_machine_covers_everything(self):
        shards = plan(1000, {"a": 1.0})
        self.assertEqual(len(shards), 1)
        self.assertEqual((shards[0]["start"], shards[0]["end"]), (0, 999))
        self.assertEqual(shards[0]["frames"], 1000)

    def test_plan_is_contiguous_and_complete(self):
        shards = plan(35230, parse_weights("m1=0.42,local=0.29,m2=0.29"))
        self.assertEqual(validate(shards, 35230), [])
        self.assertEqual(shards[0]["start"], 0)
        self.assertEqual(shards[-1]["end"], 35229)

    def test_split_points_snap_to_scene_boundaries(self):
        starts = [0, 3000, 6000, 9000]
        shards = plan(10000, {"a": 1.0, "b": 1.0}, starts, min_shard_frames=10)
        self.assertIn(shards[0]["end"] + 1, starts)

    def test_uneven_weights_give_heavier_machine_more_frames(self):
        shards = plan(10000, {"big": 0.7, "small": 0.3}, min_shard_frames=10)
        self.assertGreater(shards[0]["frames"], shards[1]["frames"])

    def test_heaviest_machine_comes_first(self):
        shards = plan(10000, {"x": 0.2, "y": 0.8}, min_shard_frames=10)
        self.assertEqual(shards[0]["name"], "y")

    def test_never_returns_empty_shards(self):
        # More machines than available frames.
        shards = plan(100, parse_weights("a=1,b=1,c=1"), min_shard_frames=150)
        self.assertEqual(len(shards), 1)
        self.assertEqual(validate(shards, 100), [])

    def test_rejects_non_positive_frames(self):
        with self.assertRaises(ValueError):
            plan(0, {"a": 1.0})


class ValidateTest(unittest.TestCase):
    def test_detects_gap(self):
        shards = [
            {"name": "a", "start": 0, "end": 99, "frames": 100, "weight": 0.5},
            {"name": "b", "start": 200, "end": 299, "frames": 100, "weight": 0.5},
        ]
        self.assertTrue(validate(shards, 300))

    def test_detects_short_coverage(self):
        shards = [{"name": "a", "start": 0, "end": 49, "frames": 50, "weight": 1.0}]
        self.assertTrue(validate(shards, 100))

    def test_empty_plan_is_invalid(self):
        self.assertTrue(validate([], 100))


if __name__ == "__main__":
    unittest.main()
