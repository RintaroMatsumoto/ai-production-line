"""System One decision gate.

Asks a decision model (no text generation) how hard the next request is, then
maps the answer to a reasoning effort. Standard library only.

    python -m src.llm.decision_gate --state "この設計をレビューして"

The endpoint speaks the System One protocol:

    POST /v1/systemone
    {"model": "...", "state": "...", "questions": {...}}

Adjust POLICY to your own traffic. The thresholds below are deliberately
asymmetric: `trivial -> low` can hurt quality, `complex -> max` only costs more.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Mapping

QUESTION = {
    "complexity": {
        "type": "choice",
        "instructions": "この依頼に必要な推論の深さは？",
        "criteria": {
            "trivial": "挨拶・定型質問・単純な変換・短い事実確認",
            "normal": "通常のコーディング・調査・要約・説明",
            "complex": "設計・難しいデバッグ・多段の推論・長い計画",
        },
    }
}

# choice -> (effort, minimum confidence, minimum margin)
POLICY: Mapping[str, tuple[str, float, float]] = {
    "trivial": ("low", 0.65, 0.50),
    "complex": ("max", 0.60, 0.25),
}

LOW_MAX_CHARS = 500
DEFAULT_TIMEOUT_S = 1.0


@dataclass(frozen=True)
class Decision:
    choice: str
    confidence: float
    margin: float
    effort: str | None
    probabilities: dict[str, float]
    latency_ms: float


def probability_margin(probabilities: Mapping[str, float]) -> float:
    """Difference between the top two probabilities (0.0 when fewer than two)."""
    values = sorted((float(v) for v in probabilities.values()), reverse=True)
    if len(values) < 2:
        return 0.0
    return values[0] - values[1]


def choose_effort(
    choice: str,
    confidence: float,
    margin: float,
    policy: Mapping[str, tuple[str, float, float]] = POLICY,
) -> str | None:
    """Return the effort to apply, or None to leave the request unchanged."""
    rule = policy.get(choice)
    if rule is None:
        return None
    effort, min_confidence, min_margin = rule
    if confidence >= min_confidence and margin >= min_margin:
        return effort
    return None


def systemone_url(endpoint: str) -> str:
    base = endpoint.rstrip("/")
    if base.endswith("/systemone"):
        return base
    return base + "/v1/systemone"


def ask(
    endpoint: str,
    state: str,
    model: str = "strands-decider-e2b",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict:
    """POST one state and one question to a System One endpoint."""
    body = json.dumps(
        {"model": model, "state": state, "questions": QUESTION}
    ).encode("utf-8")
    request = urllib.request.Request(
        systemone_url(endpoint),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def decide(
    endpoint: str,
    state: str,
    model: str = "strands-decider-e2b",
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Decision:
    started = time.perf_counter()
    payload = ask(endpoint, state, model=model, timeout=timeout)
    latency_ms = (time.perf_counter() - started) * 1000.0

    answer = (payload.get("answers") or {}).get("complexity") or {}
    probabilities = {
        str(key): float(value)
        for key, value in (answer.get("probabilities") or {}).items()
    }
    choice = str(answer.get("choice") or "")
    confidence = float(answer.get("confidence") or probabilities.get(choice, 0.0))
    margin = probability_margin(probabilities)
    effort = choose_effort(choice, confidence, margin)

    # Long inputs are never downgraded: a long request is not a trivial one.
    if effort == "low" and len(state) > LOW_MAX_CHARS:
        effort = None

    return Decision(
        choice=choice,
        confidence=confidence,
        margin=margin,
        effort=effort,
        probabilities=probabilities,
        latency_ms=latency_ms,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="System One decision gate")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8001")
    parser.add_argument("--model", default="strands-decider-e2b")
    parser.add_argument("--state", required=True)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--json", action="store_true", help="print raw decision")
    args = parser.parse_args(argv)

    try:
        decision = decide(
            args.endpoint, args.state, model=args.model, timeout=args.timeout
        )
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"decision endpoint unavailable: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "choice": decision.choice,
                    "confidence": round(decision.confidence, 4),
                    "margin": round(decision.margin, 4),
                    "effort": decision.effort,
                    "probabilities": decision.probabilities,
                    "latency_ms": round(decision.latency_ms, 1),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            f"{decision.choice} "
            f"(confidence {decision.confidence:.3f}, "
            f"margin {decision.margin:.3f}) "
            f"-> {decision.effort or 'unchanged'} "
            f"[{decision.latency_ms:.0f} ms]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
