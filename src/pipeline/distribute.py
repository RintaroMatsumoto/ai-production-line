#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Frame-range distribution planner for parallel video rendering.

The renderer is driven with ``--frames=start-end``. Splitting a single video
across machines is only safe if every split point lands on a **scene
boundary**; otherwise a line of dialogue is cut in half and the resulting
concat is silently broken (exit code 0, wrong output).

This module computes:
  1. weighted frame ranges from measured throughput ratios
  2. snapped split points (nearest scene start inside a valid window)
  3. a validation pass proving the shards are contiguous and complete

Usage:
    python -m src.pipeline.distribute --frames 35230 \
        --weights m1=0.42,local=0.29,m2=0.29 \
        --scene-json samples/scenes.example.json

    python -m src.pipeline.distribute --frames 35230 --weights a=1,b=1 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NG = 1
EXIT_USAGE = 2

# A shard shorter than this is not worth the sync/transfer overhead.
DEFAULT_MIN_SHARD_FRAMES = 150  # 5s @ 30fps


def parse_weights(spec: str) -> dict[str, float]:
    """Parse ``"a=0.5,b=0.5"`` into a normalised weight map."""
    weights: dict[str, float] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"weight must be name=value: {part!r}")
        name, value = part.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError("empty machine name in weights")
        w = float(value)
        if w <= 0:
            raise ValueError(f"weight must be positive: {name}={w}")
        weights[name] = w
    if not weights:
        raise ValueError("no weights given")
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def snap(starts: list[int], target: int, lo: int, hi: int) -> int:
    """Pick the scene start closest to *target*, constrained to [lo, hi].

    Falls back to the clamped target when no scene boundary is available.
    """
    candidates = [s for s in starts if lo <= s <= hi]
    if not candidates:
        return max(lo, min(hi, target))
    return min(candidates, key=lambda s: abs(s - target))


def plan(
    total_frames: int,
    weights: dict[str, float],
    scene_starts: list[int] | None = None,
    min_shard_frames: int = DEFAULT_MIN_SHARD_FRAMES,
) -> list[dict]:
    """Return a list of shards: ``{name, start, end, frames, weight}``."""
    if total_frames <= 0:
        raise ValueError("total_frames must be positive")

    starts = sorted(set(scene_starts or []))
    names = sorted(weights, key=lambda k: -weights[k])  # heaviest first, contiguous
    if len(names) == 1:
        return [{
            "name": names[0],
            "start": 0,
            "end": total_frames - 1,
            "frames": total_frames,
            "weight": 1.0,
        }]

    # Not enough frames to give every machine a meaningful shard.
    max_shards = max(1, total_frames // max(1, min_shard_frames))
    if len(names) > max_shards:
        names = names[:max_shards]

    bounds = [0]
    cumulative = 0.0
    for i, name in enumerate(names[:-1]):
        cumulative += weights[name]
        remaining = len(names) - i - 1
        lo = bounds[-1] + min_shard_frames
        hi = total_frames - min_shard_frames * remaining
        raw = int(round(total_frames * cumulative))
        point = snap(starts, raw, lo, hi) if starts else max(lo, min(hi, raw))
        # Guarantee strict monotonicity even with degenerate inputs.
        point = max(point, bounds[-1] + 1)
        point = min(point, total_frames - remaining)
        bounds.append(point)
    bounds.append(total_frames)

    shards = []
    for i, name in enumerate(names):
        start, end_excl = bounds[i], bounds[i + 1]
        shards.append({
            "name": name,
            "start": start,
            "end": end_excl - 1,
            "frames": end_excl - start,
            "weight": weights[name],
        })
    return shards


def validate(shards: list[dict], total_frames: int) -> list[str]:
    """Return a list of problems; empty means the plan is sound."""
    problems: list[str] = []
    if not shards:
        return ["no shards"]
    if shards[0]["start"] != 0:
        problems.append(f"first shard starts at {shards[0]['start']}, expected 0")
    if shards[-1]["end"] != total_frames - 1:
        problems.append(
            f"last shard ends at {shards[-1]['end']}, expected {total_frames - 1}")
    for a, b in zip(shards, shards[1:]):
        if b["start"] != a["end"] + 1:
            problems.append(
                f"gap/overlap between {a['name']} (end {a['end']}) "
                f"and {b['name']} (start {b['start']})")
    covered = sum(s["frames"] for s in shards)
    if covered != total_frames:
        problems.append(f"covered {covered} frames, expected {total_frames}")
    if any(s["frames"] <= 0 for s in shards):
        problems.append("a shard has no frames")
    return problems


def load_scene_starts(path: Path) -> tuple[list[int], int]:
    """Read scene starts from a scene JSON. Returns (starts, fps)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    fps = int(data.get("fps") or 30)
    gap_frames = int(round(float(data.get("gap_sec") or 0.5) * fps))
    starts = [0]
    acc = 0
    for scene in data.get("scenes") or []:
        acc += int(round(float(scene.get("duration") or 0) * fps)) + gap_frames
        starts.append(acc)
    return starts, fps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="distribute.py", description=__doc__.splitlines()[0])
    ap.add_argument("--frames", type=int, required=True, help="total frames")
    ap.add_argument("--weights", required=True,
                    help="machine weights, e.g. m1=0.42,local=0.29,m2=0.29")
    ap.add_argument("--scene-json", type=Path, default=None,
                    help="scene JSON used to snap split points to scene boundaries")
    ap.add_argument("--min-shard-frames", type=int, default=DEFAULT_MIN_SHARD_FRAMES)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    try:
        weights = parse_weights(args.weights)
    except ValueError as exc:
        print(f"[ng] {exc}", file=sys.stderr)
        return EXIT_USAGE

    starts: list[int] = []
    fps = 30
    if args.scene_json:
        if not args.scene_json.exists():
            print(f"[ng] scene json not found: {args.scene_json}", file=sys.stderr)
            return EXIT_USAGE
        starts, fps = load_scene_starts(args.scene_json)

    shards = plan(args.frames, weights, starts, args.min_shard_frames)
    problems = validate(shards, args.frames)

    if args.json:
        print(json.dumps({"fps": fps, "total_frames": args.frames,
                          "shards": shards, "problems": problems},
                         ensure_ascii=False, indent=2))
    else:
        print(f"total frames: {args.frames}  ({args.frames / fps:.2f}s @ {fps}fps)")
        print(f"{'machine':<10}{'start':>9}{'end':>9}{'frames':>9}{'sec':>9}{'share':>8}")
        for s in shards:
            share = s["frames"] / args.frames * 100
            print(f"{s['name']:<10}{s['start']:>9}{s['end']:>9}"
                  f"{s['frames']:>9}{s['frames'] / fps:>9.1f}{share:>7.1f}%")
        if problems:
            print("\n[ng] invalid plan:")
            for p in problems:
                print(f"  - {p}")
        else:
            print("\n[ok] plan is contiguous and complete")

    return EXIT_NG if problems else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
