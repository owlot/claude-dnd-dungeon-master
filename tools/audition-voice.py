#!/usr/bin/env python3
"""
Generate voice audition samples for a character.

Dispatches to the configured TTS backend (qwen3 or moss).
Backend is read from website/assets/config.json ("ttsBackend" key, default: qwen3).

Usage:
    python tools/audition-voice.py <campaign> <character> [--count N] [--backend qwen3|moss]
    python tools/audition-voice.py waterdeep-dragon-heist yagra-stonefist
    python tools/audition-voice.py waterdeep-dragon-heist yagra-stonefist --count 6

After listening, lock in your choice:
    python tools/lock-voice.py <campaign> <character> --wav <chosen_audition.wav>
"""

import sys
import os
import json
import argparse
import importlib.util


def get_backend(campaign):
    config_path = os.path.join("website", "assets", "config.json")
    config = json.loads(open(config_path).read())
    return config["ttsBackend"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", help="Campaign slug")
    parser.add_argument("character", help="Character slug")
    parser.add_argument("--count", type=int, default=4, help="Number of samples (default: 4)")
    parser.add_argument("--backend", help="Override backend: qwen3 or moss")
    args = parser.parse_args()

    backend = args.backend or get_backend(args.campaign)
    print(f"Backend: {backend}")

    voices_dir = os.path.join("website", args.campaign, "audio", "introductions")
    os.makedirs(voices_dir, exist_ok=True)

    backend_dir = os.path.join(os.path.dirname(__file__), "backends", backend)
    spec = importlib.util.spec_from_file_location("backend_audition", os.path.join(backend_dir, "audition-voice.py"))
    be = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(be)
    be.run(args.campaign, args.character, args.count, voices_dir)

    print(f"\n── Playback (5s each) ──────────────────────────")
    import glob, subprocess, time
    samples = sorted(glob.glob(os.path.join(voices_dir, f"{args.character}_audition_*.wav")))
    for path in samples:
        print(f"  {os.path.basename(path)}")
        proc = subprocess.Popen(["paplay", path])
        time.sleep(7)
        proc.terminate()
        proc.wait()

    print(f"\nDone. Lock in your choice with:")
    print(f"  python tools/lock-voice.py {args.campaign} {args.character} --wav <chosen_audition.wav>")


if __name__ == "__main__":
    main()
