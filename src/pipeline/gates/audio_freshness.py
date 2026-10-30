#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audio freshness gate.

Detects the most expensive class of automation bug: **stale artifacts that
look like successes**. A render can complete with exit code 0 while every WAV
still comes from an older script revision.

The gate does not trust settings or current text. It fingerprints what the
audio *should* contain, then compares that against a sidecar written when the
audio was actually produced.

Usage:
    python -m src.pipeline.gates.audio_freshness \
        --scenes samples/scenes.example.json --audio-dir samples/audio

    # report only, always exit 0
    python -m src.pipeline.gates.audio_freshness \
        --scenes samples/scenes.example.json --audio-dir samples/audio --report-only

Exit codes:
    0 = every WAV matches the current scene text and parameters
    1 = stale or missing WAVs (re-run the audio stage)
    3 = scenes file unreadable
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NG = 1
EXIT_GATE = 3


def fingerprint(text: str, speaker: str, params: dict) -> str:
    """Stable SHA256 over everything that affects the synthesized audio."""
    payload = json.dumps(
        {"text": text, "speaker": speaker, "params": params},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audio_path(audio_dir: Path, speaker: str, scene_id: int) -> Path:
    return audio_dir / f"{speaker}_{int(scene_id):02d}.wav"


def check(scenes_path: Path, audio_dir: Path, params: dict) -> dict:
    data = json.loads(scenes_path.read_text(encoding="utf-8-sig"))
    scenes = data.get("scenes") or []
    speaker_default = data.get("speaker_default") or "speaker"

    fresh: list[dict] = []
    stale: list[dict] = []
    missing: list[dict] = []

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("id", idx + 1)
        speaker = scene.get("speaker") or speaker_default
        text = scene.get("text") or ""
        wav = audio_path(audio_dir, speaker, scene_id)
        entry = {"scene": scene_id, "speaker": speaker, "text": text}

        if not wav.exists():
            missing.append({**entry, "reason": "WAV missing"})
            continue

        sidecar = wav.with_name(wav.name + ".fp")
        current = fingerprint(text, speaker, params)
        stored = sidecar.read_text(encoding="utf-8-sig").strip() if sidecar.exists() else None

        if stored is None:
            stale.append({**entry, "reason": "no fingerprint"})
        elif stored != current:
            stale.append({**entry, "reason": "fingerprint mismatch"})
        else:
            fresh.append(entry)

    return {
        "total": len(scenes),
        "fresh": fresh,
        "stale": stale,
        "missing": missing,
        "ok": not stale and not missing,
    }


def write_report(result: dict, report_path: Path, scenes_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    verdict = "PASS" if result["ok"] else "RE-RUN audio stage"
    lines = [
        "# Audio freshness",
        "",
        f"- scenes: `{scenes_path}`",
        f"- total: {result['total']} / fresh: {len(result['fresh'])}"
        f" / stale: {len(result['stale'])} / missing: {len(result['missing'])}",
        "",
        f"**{verdict}**",
        "",
    ]
    bad = result["stale"] + result["missing"]
    if bad:
        lines += ["| scene | speaker | reason | text |", "|---:|---|---|---|"]
        for row in bad:
            text = row["text"][:70].replace("|", "\\|")
            lines.append(
                f"| {row['scene']} | {row['speaker']} | {row['reason']} | {text} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audio_freshness.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("--scenes", type=Path, required=True)
    ap.add_argument("--audio-dir", type=Path, required=True)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--pitch", type=float, default=0.0)
    ap.add_argument("--report", type=Path, default=None,
                    help="markdown report output path")
    ap.add_argument("--report-only", action="store_true",
                    help="always exit 0 (use in reporting jobs)")
    args = ap.parse_args(argv)

    if not args.scenes.exists():
        print(f"[ng] scenes file not found: {args.scenes}", file=sys.stderr)
        return EXIT_GATE

    params = {"speed": args.speed, "pitch": args.pitch}
    result = check(args.scenes, args.audio_dir, params)

    print(f"[audio_freshness] total {result['total']} / fresh {len(result['fresh'])}"
          f" / stale {len(result['stale'])} / missing {len(result['missing'])}")
    for row in (result["stale"] + result["missing"])[:20]:
        print(f"  [ng] scene {row['scene']:>03} {row['speaker']}"
              f" {row['reason']}: {row['text'][:50]}")

    if args.report:
        write_report(result, args.report, args.scenes)
        print(f"[report] {args.report}")

    if args.report_only:
        return EXIT_OK
    return EXIT_OK if result["ok"] else EXIT_NG


if __name__ == "__main__":
    raise SystemExit(main())
