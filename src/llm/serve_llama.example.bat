@echo off
REM ==========================================================================
REM  llama.cpp server - example launcher for a 125B MoE model on a 12GB GPU
REM
REM  Copy to serve_llama.bat and adjust the paths for your machine.
REM  Never commit real paths, hostnames or credentials.
REM
REM  Key flags (see docs/02-local-llm.md):
REM    -ngl 99          offload as many layers as fit on the GPU
REM    -cmoe            keep MoE experts on the CPU
REM    -c 262144        256K context
REM    -ctk/-ctv q8_0   KV cache quantization - K and V MUST match.
REM                     Mixing them disables Flash Attention and drops
REM                     throughput from ~10.8 t/s to ~0.7 t/s at 4K context.
REM    -fa on           Flash Attention
REM    -ub 1024         physical batch. 2048 crashes on prompts >=1600 tokens.
REM ==========================================================================

set MODEL=%~dp0models\model-00001-of-00003.gguf
set LLAMA=%~dp0bin\llama-server.exe
set PORT=8080

"%LLAMA%" ^
  -m "%MODEL%" ^
  -ngl 99 -cmoe ^
  -c 262144 ^
  -ctk q8_0 -ctv q8_0 ^
  -fa on --jinja ^
  -t 32 -b 8192 -ub 1024 ^
  --host 127.0.0.1 --port %PORT% ^
  --reasoning-effort xhigh
