#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stateless production lines.

The pipeline has no queue, no workers and no state machine. **File existence is
the state**: a lesson is done for a line when that line's outputs exist.

    lesson/
      pack.json     Line 1  source gathering & distillation
      text.json     Line 2  web textbook
      test.json     Line 2  diagnostic test
      script.md     Line 3  dialogue script
      video.mp4     Line 4  rendered video
      status.json   Line 4  upload metadata (youtube_id)

Usage:
    # show what would run, in lesson-id order
    python -m src.pipeline.lines --root samples/lessons --line line2 --dry-run

    # run a command per pending lesson ({lesson} and {dir} are substituted)
    python -m src.pipeline.lines --root lessons --line line2 \
        --cmd "python tools/build_material.py --lesson {lesson}"

    # regenerate everything for one line
    python -m src.pipeline.lines --root lessons --line line2 --force --dry-run

Exit codes:
    0 = nothing failed
    1 = at least one lesson failed
    2 = usage error
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_OK, EXIT_NG, EXIT_USAGE = 0, 1, 2


@dataclass(frozen=True)
class Line:
    name: str
    description: str
    requires: tuple[str, ...]
    outputs: tuple[str, ...]


LINES: dict[str, Line] = {
    "line1": Line("資料収集＆蒸留", "collect and distil source material", (), ("pack.json",)),
    "line2": Line("教材", "web textbook, test and figures", ("pack.json",),
                  ("text.json", "test.json")),
    "line3": Line("台本", "dialogue script", ("pack.json",), ("script.md",)),
    "line4": Line("映像", "voice, direction, render, upload", ("script.md",),
                  ("video.mp4", "status.json")),
}

# BI / progress view: six stages in production order.
STAGES: tuple[tuple[str, str], ...] = (
    ("pack", "資料パック"),
    ("text", "Webテキスト"),
    ("test", "診断テスト"),
    ("script", "台本"),
    ("video", "動画"),
    ("youtube", "YouTube公開"),
)

_NUM = re.compile(r"(\d+)")


def natural_key(lesson_id: str) -> tuple:
    """Sort V3-KM1-C01-S01-L02 before ...-L10 (numeric, not lexical)."""
    return tuple(int(p) if p.isdigit() else p for p in _NUM.split(lesson_id))


def lesson_dirs(root: Path) -> list[Path]:
    """Return lesson directories (subject/lesson), sorted by lesson id."""
    found: list[Path] = []
    if not root.exists():
        return found
    for subject in sorted(p for p in root.iterdir() if p.is_dir()):
        for lesson in subject.iterdir():
            if lesson.is_dir() and any(lesson.iterdir()):
                found.append(lesson)
    return sorted(found, key=lambda p: natural_key(p.name))


def has_outputs(lesson: Path, names: tuple[str, ...]) -> bool:
    return all((lesson / n).exists() for n in names)


def line_done(lesson: Path, line: Line) -> bool:
    return has_outputs(lesson, line.outputs)


def line_ready(lesson: Path, line: Line) -> bool:
    """Upstream inputs present (an empty requires list is always ready)."""
    return has_outputs(lesson, line.requires)


def plan(root: Path, line_key: str, force: bool = False,
         limit: int | None = None) -> list[dict]:
    line = LINES[line_key]
    pending: list[dict] = []
    for lesson in lesson_dirs(root):
        if not line_ready(lesson, line):
            continue
        if line_done(lesson, line) and not force:
            continue
        pending.append({"lesson": lesson.name, "dir": str(lesson)})
        if limit is not None and len(pending) >= limit:
            break
    return pending


def run(entries: list[dict], cmd_template: str, dry_run: bool) -> tuple[int, int]:
    ok = failed = 0
    for entry in entries:
        cmd = (cmd_template
               .replace("{lesson}", entry["lesson"])
               .replace("{dir}", entry["dir"]))
        print(f"[run] {entry['lesson']}: {cmd}")
        if dry_run:
            ok += 1
            continue
        proc = subprocess.run(cmd, shell=True)
        if proc.returncode == 0:
            ok += 1
        else:
            failed += 1
            print(f"[ng] {entry['lesson']} rc={proc.returncode} (skipping, line continues)")
    return ok, failed


def progress(root: Path) -> dict:
    """Counts and average progress across the six stages (same as the BI)."""
    lessons = lesson_dirs(root)
    total = len(lessons)
    counts = {}
    for key, _label in STAGES:
        counts[key] = 0
    for lesson in lessons:
        if (lesson / "pack.json").exists():
            counts["pack"] += 1
        if (lesson / "text.json").exists():
            counts["text"] += 1
        if (lesson / "test.json").exists():
            counts["test"] += 1
        if (lesson / "script.md").exists():
            counts["script"] += 1
        if (lesson / "video.mp4").exists():
            counts["video"] += 1
        status = lesson / "status.json"
        if status.exists():
            try:
                data = json.loads(status.read_text(encoding="utf-8-sig"))
                if (data.get("line4") or {}).get("youtube_id"):
                    counts["youtube"] += 1
            except (json.JSONDecodeError, OSError):
                pass
    denominator = len(STAGES) * total
    average = (sum(counts.values()) / denominator * 100) if denominator else 0.0
    return {"lessons": total, "counts": counts, "average_percent": round(average, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lines.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, required=True, help="lessons root")
    ap.add_argument("--line", choices=sorted(LINES), default=None)
    ap.add_argument("--cmd", default=None,
                    help="command template; {lesson} and {dir} are substituted")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true",
                    help="include lessons that already have outputs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.root.exists():
        print(f"[ng] root not found: {args.root}", file=sys.stderr)
        return EXIT_USAGE

    if args.line is None:
        result = progress(args.root)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"lessons: {result['lessons']}")
            for key, label in STAGES:
                n = result["counts"][key]
                pct = (n / result["lessons"] * 100) if result["lessons"] else 0
                print(f"  {label:<14}{n:>5} / {result['lessons']:<5} {pct:5.1f}%")
            print(f"  {'平均進捗':<14}{result['average_percent']:>5.1f}%")
        return EXIT_OK

    if not args.dry_run and not args.cmd:
        print("[ng] --cmd is required unless --dry-run is given", file=sys.stderr)
        return EXIT_USAGE

    entries = plan(args.root, args.line, args.force, args.limit)
    line = LINES[args.line]
    print(f"line: {args.line} ({line.name})  pending: {len(entries)}")
    ok, failed = run(entries, args.cmd or "", args.dry_run)
    print(f"done {ok} / failed {failed}")
    return EXIT_NG if failed else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
