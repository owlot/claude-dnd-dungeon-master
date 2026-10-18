#!/usr/bin/env bash
# Install and run a tts-serve server for VoxCPM2 (voice design + cloning) on the machine with the GPU.
#   ./server-setup.sh install    one-time: clone tts-serve, create a venv, install voxcpm (needs NVIDIA driver, CUDA >= 12)
#   ./server-setup.sh run        start the server (first start downloads the openbmb/VoxCPM2 model)
#
# tts-serve has no authentication, so by default it listens on 127.0.0.1 only. From the laptop, reach it with an
# SSH tunnel:   ssh -N -L 7501:127.0.0.1:7501 <gaming-pc>      then   TTS_SERVE_URL=http://127.0.0.1:7501
# To serve the LAN instead:  VOXCPM_HOST=0.0.0.0 ./server-setup.sh run   and allow the port only from the laptop's IP.
# Engines must not share a venv, so VoxCPM gets its own. Port 7501 keeps it apart from a Qwen3 server on 7500.
set -euo pipefail
STACK="${STACK:-$HOME/tts-serve-box}"
HOST="${VOXCPM_HOST:-127.0.0.1}"
PORT="${VOXCPM_PORT:-7501}"

mkvenv() {  # python venv, falling back to uv when ensurepip is missing
  python3 -m venv "$1" 2>/dev/null && return
  rm -rf "$1"
  command -v uv >/dev/null || export PATH="$HOME/.local/bin:$PATH"
  uv venv --seed -q "$1"
}

case "${1:-}" in
  install)
    mkdir -p "$STACK"
    [ -d "$STACK/tts-serve" ] || git clone https://github.com/scorbo2/tts-serve "$STACK/tts-serve"
    [ -d "$STACK/VoxCPM/.venv" ] || { mkdir -p "$STACK/VoxCPM"; mkvenv "$STACK/VoxCPM/.venv"; }
    "$STACK/VoxCPM/.venv/bin/pip" install -q voxcpm
    "$STACK/VoxCPM/.venv/bin/pip" install -q "$STACK/tts-serve/tts-engine-common" fastapi uvicorn loguru soundfile
    "$STACK/VoxCPM/.venv/bin/python" -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
    echo "Installed. Next: $0 run"
    ;;
  run)
    echo "VoxCPM2 tts-serve on $HOST:$PORT (Ctrl-C to stop)"
    cd "$STACK/tts-serve"
    VOXCPM_HOST="$HOST" VOXCPM_PORT="$PORT" exec "$STACK/VoxCPM/.venv/bin/python" impl/server_voxcpm.py
    ;;
  *) echo "usage: $0 install|run"; exit 1 ;;
esac
