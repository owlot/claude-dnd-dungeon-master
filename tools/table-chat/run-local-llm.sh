#!/usr/bin/env bash
# Start the local LLM that table chat drafts with (config.json points table chat at http://127.0.0.1:8081).
# Qwen3.8 27B, GSQ-RCO IQ3_S (about 12 GB), fully on the GPU; 3 request slots of 8192 tokens.
# Stop it with: pkill -f 'llama-server.*--port 8081'
set -euo pipefail
MODEL="${LOCAL_LLM_MODEL:-$(ls "$HOME"/.cache/huggingface/hub/models--ISTA-DASLab--Qwen3.8-27B-GSQ-RCO-GGUF/snapshots/*/Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf | head -1)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
LLAMA_SERVER="${LLAMA_SERVER:-$(command -v llama-server || true)}"
[ -n "$LLAMA_SERVER" ] || { echo "llama-server not found: install llama.cpp or set LLAMA_SERVER=/path/to/llama-server"; exit 1; }
LOGS="$HERE/.logs"; mkdir -p "$LOGS"
if curl -sf -m 2 http://127.0.0.1:8081/health >/dev/null; then echo "already running on 8081"; exit 0; fi
nohup "$LLAMA_SERVER" -m "$MODEL" -ngl 99 -c 24576 -np 3 -fa on --jinja \
  --host 127.0.0.1 --port 8081 --alias local-npc >"$LOGS/llama-local.log" 2>&1 &
echo "started (pid $!); log: $LOGS/llama-local.log"
