#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage orchestrator.

Runs a video unit through 16 stages, resumably. Production commands live in a
JSON config so this file stays environment-agnostic:

    {
      "stages": {
        "script":  {"cmd": ["python", "tools/make_script.py", "{unit}"]},
        "audio":   {"cmd": ["python", "tools/synthesize.py", "{unit}"]},
        "render":  {"cmd": ["python", "tools/render.py", "{unit}"]}
      }
    }

Stages without a configured command are reported as ``n/a`` and skipped, which
is what happens in this public edition (the original tooling is private).

Usage:
    python -m src.pipeline.orchestrator --unit DEMO-01 --dry-run
    python -m src.pipeline.orchestrator --unit DEMO-01 --from audio --to qa
    python -m src.pipeline.orchestrator --unit DEMO-01 --config my.json --workdir out

Exit codes:
    0 = all requested stages succeeded
    1 = a stage failed
    2 = usage error
    3 = a gate rejected the output
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK, EXIT_NG, EXIT_USAGE, EXIT_GATE = 0, 1, 2, 3


@dataclass(frozen=True)
class Stage:
    name: str
    description: str
    output: str
    gate: bool = False


STAGES: list[Stage] = [
    Stage("lecture",      "analyse reference lectures",            "reports/lecture.md"),
    Stage("survey",       "collect source material",               "work/survey.json"),
    Stage("spec",         "outline and learning objectives",       "work/spec.json"),
    Stage("design",       "lesson design / visual patterns",       "work/design.json"),
    Stage("script",       "generate dialogue script",              "work/script.json"),
    Stage("quality",      "script QA (mechanical + rubric)",       "work/quality.json", gate=True),
    Stage("scene",        "split into timed scenes",               "work/scenes.json"),
    Stage("visuals",      "plan and generate SVG figures",         "work/visuals/"),
    Stage("reading",      "apply reading dictionary",              "work/readings.json"),
    Stage("audio",        "synthesize speech per scene",           "work/audio/"),
    Stage("assets",       "build character / lip-sync assets",     "work/assets/"),
    Stage("presentation", "subtitles, chapter UI, transitions",    "work/presentation.json"),
    Stage("thumbnail",    "generate thumbnail",                    "work/thumbnail.png"),
    Stage("render",       "render video",                          "work/out/{unit}.mp4"),
    Stage("qa",           "final QA (edges, duration, silence)",   "work/qa.json", gate=True),
    Stage("progress",     "update ledger and pick next unit",      "work/progress.json"),
]

STAGE_INDEX = {s.name: i for i, s in enumerate(STAGES)}


@dataclass
class Plan:
    unit: str
    stages: list[Stage] = field(default_factory=list)
    skipped: list[Stage] = field(default_factory=list)
    unconfigured: list[Stage] = field(default_factory=list)


def load_config(path: Path | None) -> dict:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("stages") or {}


def build_plan(unit: str, config: dict, from_stage: str | None,
               to_stage: str | None) -> Plan:
    lo = STAGE_INDEX[from_stage] if from_stage else 0
    hi = STAGE_INDEX[to_stage] if to_stage else len(STAGES) - 1
    if lo > hi:
        raise ValueError(f"--from {from_stage} comes after --to {to_stage}")

    plan = Plan(unit=unit)
    for stage in STAGES[lo:hi + 1]:
        cmd = (config.get(stage.name) or {}).get("cmd")
        if not cmd:
            plan.unconfigured.append(stage)
        else:
            plan.stages.append(stage)
    return plan


def render_cmd(cmd: list[str], unit: str) -> list[str]:
    return [str(part).replace("{unit}", unit) for part in cmd]


def print_plan(plan: Plan, config: dict) -> None:
    print(f"unit: {plan.unit}")
    print(f"{'#':>3}  {'stage':<13}{'kind':<7}{'output':<32}description")
    print("-" * 92)
    for i, stage in enumerate(STAGES, 1):
        if stage in plan.stages:
            kind = "gate" if stage.gate else "run"
        elif stage in plan.unconfigured:
            kind = "n/a"
        else:
            kind = "-"
        out = stage.output.format(unit=plan.unit)
        print(f"{i:>3}  {stage.name:<13}{kind:<7}{out:<32}{stage.description}")


def run_plan(plan: Plan, config: dict, workdir: Path, dry_run: bool) -> int:
    workdir.mkdir(parents=True, exist_ok=True)
    for stage in plan.stages:
        cmd = render_cmd((config.get(stage.name) or {}).get("cmd") or [], plan.unit)
        print(f"\n[stage] {stage.name}: {' '.join(cmd)}")
        if dry_run:
            continue
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, cwd=workdir)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            code = EXIT_GATE if stage.gate else EXIT_NG
            print(f"[ng] {stage.name} failed rc={proc.returncode} "
                  f"after {elapsed:.1f}s")
            if stage.gate:
                print("[hint] gate failure = content problem, not a crash. "
                      "Fix the artifact, then re-run from this stage.")
            else:
                print("[hint] re-run with --from "
                      f"{stage.name} after fixing the cause.")
            return code
        print(f"[ok] {stage.name} ({elapsed:.1f}s)")

    if plan.unconfigured:
        print(f"\n[i] {len(plan.unconfigured)} stage(s) have no command configured "
              "in this public edition: "
              + ", ".join(s.name for s in plan.unconfigured))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="orchestrator.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("--unit", required=True)
    ap.add_argument("--from", dest="from_stage", default=None,
                    choices=[s.name for s in STAGES])
    ap.add_argument("--to", dest="to_stage", default=None,
                    choices=[s.name for s in STAGES])
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--workdir", type=Path, default=Path("work"))
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without executing anything")
    args = ap.parse_args(argv)

    try:
        config = load_config(args.config)
        plan = build_plan(args.unit, config, args.from_stage, args.to_stage)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"[ng] {exc}", file=sys.stderr)
        return EXIT_USAGE

    print_plan(plan, config)
    if args.dry_run:
        print("\n[dry-run] nothing executed")
        return EXIT_OK
    return run_plan(plan, config, args.workdir, dry_run=False)


if __name__ == "__main__":
    raise SystemExit(main())
