#!/usr/bin/env python3
"""
Generate narrator voice audition samples.

Dispatches to the configured TTS backend (qwen3 or moss).
The narrator is global and stored at website/audio/introductions/.

Usage:
    python tools/audition-narrator.py [--count N] [--backend qwen3|moss]

After listening, lock in your choice:
    python tools/lock-voice.py narrator website/audio/introductions/narrator_audition_N.wav
"""

import sys
import os
import argparse
import importlib.util


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=4, help="Number of samples (default: 4)")
    parser.add_argument("--backend", default="qwen3", help="Backend: qwen3 or moss (default: qwen3)")
    args = parser.parse_args()

    print(f"Backend: {args.backend}")

    voices_dir = "website/audio/introductions"
    os.makedirs(voices_dir, exist_ok=True)

    backend_dir = os.path.join(os.path.dirname(__file__), "backends", args.backend)
    spec = importlib.util.spec_from_file_location("backend_narrator", os.path.join(backend_dir, "audition-narrator.py"))
    be = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(be)
    be.run(args.count, voices_dir)

    print(f"\nDone. Lock in your choice with:")
    print(f"  python tools/lock-voice.py narrator website/audio/introductions/narrator_audition_N.wav")


if __name__ == "__main__":
    main()
