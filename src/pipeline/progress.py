#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Progress from file existence — the same metric the BI dashboard shows.

Six stages: pack / text / test / script / video / youtube.

    average = (sum of stage counts) / (6 * lessons) * 100

A lesson reaches 100% only when its video is rendered *and* published.
"4-point set" (pack + text + test + script) is deliberately not the same thing.

Usage:
    python -m src.pipeline.progress --root samples/lessons
    python -m src.pipeline.progress --root samples/lessons --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.pipeline.lines import STAGES, progress

EXIT_OK, EXIT_USAGE = 0, 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="progress.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.root.exists():
        print(f"[ng] root not found: {args.root}", file=sys.stderr)
        return EXIT_USAGE

    result = progress(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_OK

    total = result["lessons"]
    print(f"lessons: {total}")
    print(f"{'stage':<16}{'done':>6}{'total':>7}{'rate':>8}")
    for key, label in STAGES:
        n = result["counts"][key]
        pct = (n / total * 100) if total else 0
        print(f"{label:<16}{n:>6}{total:>7}{pct:>7.1f}%")
    print(f"{'平均進捗':<16}{'':>6}{'':>7}{result['average_percent']:>7.1f}%")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
