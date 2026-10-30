#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate demo audio for the freshness gate.

Creates a silent WAV and a matching ``.fp`` sidecar for every scene, so the
gate passes. Then edit any ``text`` in the scene JSON and run the gate again:
the same WAV is suddenly reported as stale. That is the bug class the gate
exists to catch.

Usage:
    python samples/make_demo_audio.py
    python samples/make_demo_audio.py --texts scenes.json --audio-dir other/audio
"""
from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline.gates.audio_freshness import fingerprint  # noqa: E402

DEFAULT_PARAMS = {"speed": 1.0, "pitch": 0.0}


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--texts", type=Path, default=here / "scenes.example.json")
    ap.add_argument("--audio-dir", type=Path, default=here / "audio")
    ap.add_argument("--rate", type=int, default=24000)
    args = ap.parse_args(argv)

    data = json.loads(args.texts.read_text(encoding="utf-8"))
    fps = int(data.get("fps") or 30)
    speaker_default = data.get("speaker_default") or "speaker"
    args.audio_dir.mkdir(parents=True, exist_ok=True)

    for idx, scene in enumerate(data.get("scenes") or []):
        scene_id = scene.get("id", idx + 1)
        speaker = scene.get("speaker") or speaker_default
        text = scene.get("text") or ""
        duration = float(scene.get("duration") or 1.0)
        wav_path = args.audio_dir / f"{speaker}_{int(scene_id):02d}.wav"

        frames = int(duration * args.rate)
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(args.rate)
            w.writeframes(b"\x00\x00" * frames)

        sidecar = wav_path.with_name(wav_path.name + ".fp")
        sidecar.write_text(fingerprint(text, speaker, DEFAULT_PARAMS),
                           encoding="utf-8")
        print(f"  {wav_path.name}  {duration:.1f}s  ({duration * fps:.0f} frames)")

    print(f"\n[demo] wrote {len(data.get('scenes') or [])} WAVs to {args.audio_dir}")
    print("[next] python -m src.pipeline.gates.audio_freshness "
          f"--scenes {args.texts.relative_to(ROOT)} "
          f"--audio-dir {args.audio_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
