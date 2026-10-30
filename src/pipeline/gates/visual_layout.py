#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Visual layout gate.

Generated SVG/HTML looks fine in isolation and breaks on the canvas: text
overflows the edge, or the figure drifts away from center. Text width depends
on the font, so it cannot be predicted at generation time — it has to be
measured after rendering.

This gate consumes measured bounding boxes and checks:

  * overflow   — no element may extend outside the canvas
  * centering  — the union box center must sit within ±tolerance px
  * coverage   — a scene must contain at least one visual

Usage:
    python -m src.pipeline.gates.visual_layout samples/layout.example.json
    python -m src.pipeline.gates.visual_layout samples/layout.example.json --tolerance 16

Exit codes:
    0 = pass
    3 = gate failed (layout problem)
    2 = usage / unreadable input
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_GATE = 3

DEFAULT_TOLERANCE = 12  # px


def union_bbox(boxes: list[list[float]]) -> list[float]:
    xs = [b[0] for b in boxes]
    ys = [b[1] for b in boxes]
    xe = [b[0] + b[2] for b in boxes]
    ye = [b[1] + b[3] for b in boxes]
    x, y = min(xs), min(ys)
    return [x, y, max(xe) - x, max(ye) - y]


def evaluate(layout: dict, tolerance: float = DEFAULT_TOLERANCE) -> dict:
    canvas = layout.get("canvas") or {}
    cw, ch = float(canvas.get("w") or 0), float(canvas.get("h") or 0)
    elements = layout.get("elements") or []

    problems: list[str] = []

    if cw <= 0 or ch <= 0:
        return {"ok": False, "problems": ["canvas size missing or invalid"],
                "overflow": [], "offset": None}

    if not elements:
        return {"ok": False, "problems": ["no visual elements in this scene"],
                "overflow": [], "offset": None}

    overflow = []
    for el in elements:
        name = el.get("id") or "element"
        x, y, w, h = (float(v) for v in el["bbox"])
        if x < 0 or y < 0 or x + w > cw or y + h > ch:
            overflow.append(name)
            problems.append(
                f"{name} overflows canvas: bbox=({x:.1f},{y:.1f},{w:.1f},{h:.1f}) "
                f"canvas=({cw:.0f}x{ch:.0f})")

    box = union_bbox([el["bbox"] for el in elements])
    dx = (box[0] + box[2] / 2) - cw / 2
    dy = (box[1] + box[3] / 2) - ch / 2
    if abs(dx) > tolerance or abs(dy) > tolerance:
        problems.append(
            f"figure is off-center by ({dx:+.1f}, {dy:+.1f}) px "
            f"(tolerance ±{tolerance:g})")

    return {
        "ok": not problems,
        "problems": problems,
        "overflow": overflow,
        "offset": {"dx": round(dx, 2), "dy": round(dy, 2)},
        "union_bbox": [round(v, 2) for v in box],
        "canvas": {"w": cw, "h": ch},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="visual_layout.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("layout", type=Path)
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                    help="allowed center offset in px (default 12)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        layout = json.loads(args.layout.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ng] cannot read layout: {exc}", file=sys.stderr)
        return EXIT_USAGE

    result = evaluate(layout, args.tolerance)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["offset"]:
            print(f"[layout] canvas {result['canvas']['w']:.0f}x"
                  f"{result['canvas']['h']:.0f}  offset "
                  f"({result['offset']['dx']:+.1f}, {result['offset']['dy']:+.1f})px")
        if result["ok"]:
            print("[ok] no overflow, centered")
        else:
            for p in result["problems"]:
                print(f"[ng] {p}")

    return EXIT_OK if result["ok"] else EXIT_GATE


if __name__ == "__main__":
    raise SystemExit(main())
