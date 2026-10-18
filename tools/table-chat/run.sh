#!/usr/bin/env bash
# Start the table chat server on the DM's machine (the laptop). Stop it with Ctrl-C.
# It listens on 127.0.0.1 only; the tablet reaches it through `tailscale serve` (see README.md).
#
# Hot reload is ON: when a Python file the server uses changes (server.py, .claude/scripts, the voice backends), the server restarts
# itself and picks the live conversation up again from disk, so new features appear without stopping anything.
# (The open pages keep a live connection to the server; without --timeout-graceful-shutdown the old process would wait for them forever.)
# Turn it off with `run.sh --no-reload` or TABLE_CHAT_RELOAD=0 (then restart by hand after updates).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
UV="$HERE/.venv/bin/uvicorn"                     # this folder's own venv (created with: uv venv .venv && uv pip install -r requirements.txt)
[ -x "$UV" ] || { echo "No .venv here: run  cd $HERE && uv venv .venv --python 3.14 && uv pip install --python .venv/bin/python -r requirements.txt"; exit 1; }
# settings.yaml is yours (ignored by git); the first run starts it from the example
if [ ! -f "$HERE/settings.yaml" ]; then
  cp "$HERE/settings.example.yaml" "$HERE/settings.yaml"
  echo "Created $HERE/settings.yaml from settings.example.yaml: edit the llm, stt and tts addresses in it, then restart."
fi
export TABLE_CHAT_PORT="${TABLE_CHAT_PORT:-8020}"
RELOAD=1
[ "${TABLE_CHAT_RELOAD:-1}" = "0" ] && RELOAD=0
for a in "$@"; do [ "$a" = "--no-reload" ] && RELOAD=0; done
ARGS=()
if [ "$RELOAD" = 1 ]; then
  ARGS=(--timeout-graceful-shutdown 2 --reload --reload-dir "$HERE" --reload-dir "$REPO/.claude/scripts" --reload-dir "$REPO/.claude/tools/backends" --reload-include '*.py')
  echo "Hot reload is on: editing the server restarts it and keeps the live conversation."
fi
cd "$HERE"
echo "Table chat on http://127.0.0.1:$TABLE_CHAT_PORT  (the DM link with its key is printed below)"
command -v tailscale >/dev/null && echo "Tablet: run once in another terminal:  tailscale serve --bg $TABLE_CHAT_PORT   then open the https://…ts.net address it prints"
exec "$UV" server:app --host 127.0.0.1 --port "$TABLE_CHAT_PORT" ${ARGS[@]+"${ARGS[@]}"}
