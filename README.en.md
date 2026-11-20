# AI Production Line

**A generative media stack that runs entirely on local GPUs.**

Image and video generation with ComfyUI in Docker, a local LLM, speech synthesis,
rendering, a delivery layer and an operations dashboard — in one repository.
No external generation API. Models, inputs and outputs stay on the machines.

[![CI](https://github.com/RintaroMatsumoto/ai-production-line/actions/workflows/ci.yml/badge.svg)](https://github.com/RintaroMatsumoto/ai-production-line/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/runtime%20deps-none-success)](requirements.txt)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[日本語 README](README.md) · [Architecture](docs/01-architecture.md) · [Generation](docs/03-video-pipeline.md) · [Delivery](docs/07-website.md) · [BI](docs/08-bi-dashboard.md)

## Why local

Cloud generation APIs are convenient, but they are a poor foundation for a production line:

| Constraint | What local buys you |
|---|---|
| Per-call pricing | Electricity only — thousands of attempts cost the same |
| Rate limits and queueing | Two GPUs you can saturate whenever you want |
| Inputs and outputs leave your machine | Nothing leaves the box |

The point of this stack is to **decouple the number of attempts from cost**.

## Stack

| Layer | Technology |
|---|---|
| Image / video generation | **ComfyUI in Docker** (ai-dock base), SDXL, Flux, Wan 2.2, AnimateDiff |
| Consistency | LoRA (kohya_ss), IP-Adapter FaceID, ControlNet, ReActor |
| Post-processing | Real-ESRGAN, RIFE frame interpolation, LivePortrait / SadTalker / Wav2Lip |
| LLM | llama.cpp (125B MoE, 256K context, 12GB VRAM) |
| Speech | VOICEVOX (local HTTP) |
| Video assembly | Remotion (React → MP4) |
| Orchestration | Python (standard library only) |
| Delivery | Static SPA + PWA (no server) |
| Observability | Local BI (stdlib + bundled Chart.js) |
| Runtime | Docker with GPU passthrough, Windows 11 |

## Measured numbers

| Metric | Value | Environment |
|---|---|---|
| Image generation | **~4 s / image** | RTX 3080 10GB, SDXL |
| Image generation | ~12 s / image | RTX 3060 12GB, SDXL |
| Video generation | **~5 s / clip** | RTX 3080, Wan 2.2 TI2V 5B, 832×480 |
| Video generation | ~10 s / clip | RTX 3060, same model |
| LoRA training | 2.40 s/it | RTX 3060, SDXL, kohya_ss |
| LLM inference | 10.8 t/s @ 256K context | RTX 3060, 125B MoE |
| Video render | 2 machines in parallel | Remotion |
| External generation APIs | **0** | everything local |

## Three highlights

**1. ComfyUI as a reproducible Docker service.**
One image, two machines. Custom-node dependencies pinned, Triton + SageAttention
for a 20–30% speedup, models and outputs on separate named volumes, and
`--lowvram --force-fp16` to fit 10–12GB of VRAM.

**2. Generation as a line, not a session.**
Four independent CLI stages, no queue, no workers, no state machine.
Progress is file existence. A failed unit is logged and skipped; the line keeps going.
Rerunning resumes at the first unfinished unit.

**3. Generation, delivery and observability in one loop.**
Outputs ship as a static SPA + PWA (no DB, no API), and a one-command local BI
shows per-stage progress, line health, cost and failures.

## Architecture

```mermaid
flowchart TB
  subgraph LOCAL["Local machine (no external APIs)"]
    subgraph GEN["Generation"]
      C["ComfyUI<br/>Docker + GPU"]
      L["llama.cpp<br/>local LLM"]
      V["VOICEVOX"]
    end
    subgraph LINES["4 stateless lines"]
      A1["collect"] --> A2["pack.json"]
      A2 --> B1["structure"]
      A2 --> C1["script"]
      C1 --> D1["render"]
    end
    R["Remotion<br/>2 machines"]
    S["Static SPA + PWA"]
    BI["Local BI"]
  end
  C --> D1
  L --> A2
  L --> B1
  V --> D1
  D1 --> R
  B1 --> S
  A2 --> BI
  B1 --> BI
  D1 --> BI
```

## Quick start

No runtime dependencies.

```bash
python -m src.pipeline.lines --root samples/lessons --line line2 --dry-run
python -m src.pipeline.progress --root samples/lessons

python samples/make_demo_audio.py
python -m src.pipeline.gates.audio_freshness \
  --scenes samples/scenes.example.json --audio-dir samples/audio
python -m src.pipeline.gates.visual_layout samples/layout.example.json

python -m unittest discover -s tests -v
```

## What is not included

A public edition of a private system. Removed: model files and LoRAs, source
material, generated output, credentials, internal hostnames, production prompts
and character definitions.

Included: design decisions, the Docker setup, generalized implementations,
measured numbers, and a failure log.

## License

Code: [MIT](LICENSE). Documentation: CC BY 4.0.

---

**Rintaro Matsumoto** — 22 years in the Japan Ground Self-Defense Force working
on communications infrastructure and combat simulation systems. Currently
building local-first generative media infrastructure.
