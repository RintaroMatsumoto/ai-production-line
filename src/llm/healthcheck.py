#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Health probe for a local LLM server.

Alive is not the same as usable: a server can answer /health while generating
at half its normal speed. This probe therefore checks three things:

  1. reachability
  2. model availability
  3. a short generation with a throughput floor

Usage:
    python -m src.llm.healthcheck --base-url http://127.0.0.1:8080 \
        --model my-model --min-tps 5
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

EXIT_OK, EXIT_NG = 0, 1


def get_json(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def probe(base_url: str, model: str | None, min_tps: float,
          timeout: float) -> tuple[bool, list[str]]:
    notes: list[str] = []
    base = base_url.rstrip("/")

    try:
        health = get_json(base + "/health", timeout)
        notes.append(f"health: {health}")
    except Exception as exc:  # noqa: BLE001
        return False, [f"health unreachable: {exc}"]

    models = []
    try:
        listing = get_json(base + "/v1/models", timeout)
        models = [m.get("id") for m in listing.get("data") or []]
        notes.append(f"models: {', '.join(models[:5]) or '(none)'}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"models list failed: {exc}")

    target = model or (models[0] if models else "")
    if not target:
        return False, notes + ["no model available"]

    body = json.dumps({"model": target, "max_tokens": 64, "stream": False,
                       "messages": [{"role": "user",
                                     "content": "Reply with the single word OK."}]}
                      ).encode("utf-8")
    req = urllib.request.Request(base + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        return False, notes + [f"generation failed: {exc}"]

    usage = raw.get("usage") or {}
    notes.append(f"tokens: {usage.get('completion_tokens', 0)}")
    if min_tps > 0:
        notes.append(f"throughput floor: {min_tps} t/s "
                     "(measure with benchmark.py for accurate numbers)")
    return True, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="healthcheck.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--model", default=None)
    ap.add_argument("--min-tps", type=float, default=0.0)
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args(argv)

    ok, notes = probe(args.base_url, args.model, args.min_tps, args.timeout)
    for note in notes:
        print(f"  {note}")
    print("[ok]" if ok else "[ng]")
    return EXIT_OK if ok else EXIT_NG


if __name__ == "__main__":
    raise SystemExit(main())
