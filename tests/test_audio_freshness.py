"""Tests for the audio freshness gate."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from src.pipeline.gates.audio_freshness import check, fingerprint

PARAMS = {"speed": 1.0, "pitch": 0.0}


def write_scenes(path: Path, scenes: list[dict]) -> None:
    path.write_text(json.dumps({"fps": 30, "scenes": scenes}, ensure_ascii=False),
                    encoding="utf-8")


def write_audio(audio_dir: Path, speaker: str, scene_id: int, text: str) -> None:
    audio_dir.mkdir(parents=True, exist_ok=True)
    wav = audio_dir / f"{speaker}_{scene_id:02d}.wav"
    wav.write_bytes(b"RIFF....WAVE")  # content is irrelevant to the gate
    wav.with_name(wav.name + ".fp").write_text(
        fingerprint(text, speaker, PARAMS), encoding="utf-8")


class AudioFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scenes = self.root / "scenes.json"
        self.audio = self.root / "audio"

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_fresh(self):
        scenes = [{"id": 1, "speaker": "zun", "text": "こんにちは"}]
        write_scenes(self.scenes, scenes)
        write_audio(self.audio, "zun", 1, "こんにちは")
        result = check(self.scenes, self.audio, PARAMS)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["fresh"]), 1)

    def test_detects_text_change(self):
        scenes = [{"id": 1, "speaker": "zun", "text": "こんにちは"}]
        write_scenes(self.scenes, scenes)
        write_audio(self.audio, "zun", 1, "こんにちは")
        # The script was edited but audio was not regenerated.
        write_scenes(self.scenes, [{"id": 1, "speaker": "zun", "text": "こんばんは"}])
        result = check(self.scenes, self.audio, PARAMS)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stale"][0]["reason"], "fingerprint mismatch")

    def test_detects_missing_wav(self):
        write_scenes(self.scenes, [{"id": 1, "speaker": "zun", "text": "a"}])
        result = check(self.scenes, self.audio, PARAMS)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["missing"]), 1)

    def test_detects_missing_sidecar(self):
        write_scenes(self.scenes, [{"id": 1, "speaker": "zun", "text": "a"}])
        self.audio.mkdir(parents=True)
        (self.audio / "zun_01.wav").write_bytes(b"RIFF....WAVE")
        result = check(self.scenes, self.audio, PARAMS)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stale"][0]["reason"], "no fingerprint")

    def test_parameter_change_invalidates(self):
        write_scenes(self.scenes, [{"id": 1, "speaker": "zun", "text": "a"}])
        write_audio(self.audio, "zun", 1, "a")
        result = check(self.scenes, self.audio, {"speed": 1.2, "pitch": 0.0})
        self.assertFalse(result["ok"])

    def test_fingerprint_is_stable_and_sensitive(self):
        self.assertEqual(fingerprint("a", "zun", PARAMS),
                         fingerprint("a", "zun", PARAMS))
        self.assertNotEqual(fingerprint("a", "zun", PARAMS),
                            fingerprint("a", "metan", PARAMS))

    def test_reads_utf8_bom(self):
        """Windows editors commonly save JSON with a BOM; do not crash on it."""
        write_scenes(self.scenes, [{"id": 1, "speaker": "zun", "text": "a"}])
        write_audio(self.audio, "zun", 1, "a")
        raw = self.scenes.read_bytes()
        self.scenes.write_bytes(b"\xef\xbb\xbf" + raw)
        result = check(self.scenes, self.audio, PARAMS)
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
