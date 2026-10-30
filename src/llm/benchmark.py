#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Throughput / quality benchmark for an OpenAI-compatible LLM server.

Measures tokens per second and checks answers automatically, so quantization
changes can be compared without relying on vibes. Five prompt families cover
reasoning, code, Japanese style, summarization and long-context recall.

Usage:
    python -m src.llm.benchmark --base-url http://127.0.0.1:8080 --model my-model
    python -m src.llm.benchmark --base-url http://127.0.0.1:8080 \
        --model my-model --quant q8_0 --out results.json

The server must expose ``POST /v1/chat/completions`` and ``GET /health``
(llama.cpp server, vLLM, LM Studio, etc.).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

EXIT_OK, EXIT_NG = 0, 1

PROMPTS = [
    {
        "id": "reasoning",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": (
            "A bat and a ball cost $1.10 in total. The bat costs $1.00 more "
            "than the ball. How much does the ball cost? Think step by step, "
            "then give only the final numeric answer in dollars.")}],
        "check": lambda c: "0.05" in c,
    },
    {
        "id": "code",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": (
            "Write a Python function `merge_sorted(a, b)` that merges two "
            "sorted lists into one sorted list without using sorted()/sort(). "
            "Include type hints. Output only code.")}],
        "check": lambda c: ("def merge_sorted" in c
                            and "sorted(" not in c.replace("merge_sorted", "FN")),
    },
    {
        "id": "ja_polite",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": (
            "「データを取って解析する」をビジネス向けの丁寧な日本語に"
            "書き直してください。一文のみ。")}],
        "check": lambda c: (("ください" in c or "いたします" in c or "ます" in c)
                            and "取って" not in c),
    },
    {
        "id": "summarize",
        "max_tokens": 512,
        "messages": [{"role": "user", "content": (
            "Summarize in exactly 3 bullets: LLM quantization reduces model "
            "size by replacing weights with lower-bit representations. KV cache "
            "quantization targets the attention key/value cache instead. "
            "Aggressive KV quant may degrade long-context quality while saving RAM.")}],
        "check": lambda c: (c.count("-") + c.count("•") + c.count("*") >= 3
                            or c.count("\n") >= 3),
    },
    {
        "id": "longctx_needle",
        "max_tokens": 512,
        "messages": [
            {"role": "user", "content": (
                "The secret code for the vault is ALPHA-BRAVO-77. "
                "Ignore all other numbers. Confirm you understood by replying OK only.")},
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": (
                "Filler text: " + ("The quick brown fox jumps over the lazy dog. " * 200)
                + "\n\nWhat is the secret code for the vault? Answer with just the code.")},
        ],
        "check": lambda c: "alpha-bravo-77" in c.lower(),
    },
]


def chat(base_url: str, model: str, messages: list[dict], max_tokens: int,
         timeout: float) -> dict:
    body = json.dumps({"model": model, "messages": messages,
                       "max_tokens": max_tokens, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read())
    dt = time.perf_counter() - t0

    choice = (raw.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = raw.get("usage") or {}
    completed = int(usage.get("completion_tokens") or 0)
    return {
        "seconds": round(dt, 3),
        "tps": round(completed / dt, 2) if dt > 0 else 0.0,
        "completion_tokens": completed,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "finish_reason": choice.get("finish_reason", ""),
        "content": message.get("content") or "",
        "reasoning_chars": len(message.get("reasoning_content") or ""),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchmark.py",
                                 description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--model", required=True)
    ap.add_argument("--quant", default="", help="label for this run, e.g. q8_0")
    ap.add_argument("--out", type=Path, default=None, help="append results as JSON")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--skip-health", action="store_true")
    args = ap.parse_args(argv)

    if not args.skip_health:
        try:
            with urllib.request.urlopen(
                    args.base_url.rstrip("/") + "/health", timeout=10) as r:
                print(f"health={json.loads(r.read())}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"[warn] health check failed: {exc}")

    results = []
    ok = 0
    for prompt in PROMPTS:
        try:
            r = chat(args.base_url, args.model, prompt["messages"],
                     prompt["max_tokens"], args.timeout)
            r["id"] = prompt["id"]
            r["answer_ok"] = bool(prompt["check"](r["content"]))
            ok += int(r["answer_ok"])
            print(f"  {prompt['id']:<16}{r['tps']:>7.2f} t/s  "
                  f"ok={r['answer_ok']!s:<5} {r['completion_tokens']:>5} tok  "
                  f"{r['seconds']:>7.2f}s")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            r = {"id": prompt["id"], "error": str(exc)}
            print(f"  {prompt['id']:<16}ERROR {exc}")
        results.append(r)

    print(f"\nanswer_ok {ok}/{len(PROMPTS)}  quant={args.quant or '-'}")
    if args.out:
        payload = {"model": args.model, "quant": args.quant,
                   "base_url": args.base_url, "results": results}
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"[saved] {args.out}")
    return EXIT_OK if ok == len(PROMPTS) else EXIT_NG


if __name__ == "__main__":
    raise SystemExit(main())
