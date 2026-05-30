#!/usr/bin/env python3
"""
Lock in a voice for a character or narrator.

Dispatches to the configured TTS backend (qwen3 or moss).
Backend is read from website/assets/config.json ("ttsBackend" key, default: qwen3).

Qwen3: generates .wav + .pt ICL clone prompt (reference audio + transcript embedding)
MOSS:  renders introduction text via MOSS-TTS, saves as .wav reference

Usage:
    python tools/lock-voice.py <campaign> <character> [--wav <path>] [--backend qwen3|moss]
    python tools/lock-voice.py waterdeep-dragon-heist yagra-stonefist
    python tools/lock-voice.py waterdeep-dragon-heist yagra-stonefist --wav .../yagra_audition_4.wav

    # Narrator (no introduction rendering — just copy + build prompt):
    python tools/lock-voice.py narrator <wav-path> [--backend qwen3|moss]
    python tools/lock-voice.py narrator website/audio/introductions/narrator_audition_1.wav
"""

import sys
import os
import glob
import json
import argparse
import importlib.util


def update_index(out_dir):
    wavs = glob.glob(os.path.join(out_dir, "*.wav"))
    slugs = sorted(
        os.path.splitext(os.path.basename(w))[0]
        for w in wavs
        if not any(x in os.path.basename(w) for x in ("_ref", "_audition_"))
        and not os.path.basename(w).startswith(("male-", "female-"))
    )
    index_path = os.path.join(out_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(slugs, f, indent=2)
    print(f"Updated: {index_path} ({len(slugs)} entries)")


def get_backend(campaign):
    config_path = os.path.join("website", "assets", "config.json")
    config = json.loads(open(config_path).read())
    return config["ttsBackend"]


def load_backend(backend):
    backend_dir = os.path.join(os.path.dirname(__file__), "backends", backend)
    spec = importlib.util.spec_from_file_location("backend_lock", os.path.join(backend_dir, "lock-voice.py"))
    be = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(be)
    return be


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arg1", help="'narrator' or campaign slug")
    parser.add_argument("arg2", nargs="?", help="character slug (or wav path for narrator)")
    parser.add_argument("--wav", help="Specific audition WAV to use as reference")
    parser.add_argument("--backend", help="Override backend: qwen3 or moss")
    args = parser.parse_args()

    # ---- Narrator mode ----
    if args.arg1 == "narrator":
        wav_path = args.arg2 or args.wav
        if not wav_path or not os.path.exists(wav_path):
            print("Error: provide a wav path for narrator")
            sys.exit(1)
        backend = args.backend or "qwen3"
        print(f"Backend: {backend}")
        out_dir = "website/audio/introductions"
        os.makedirs(out_dir, exist_ok=True)
        be = load_backend(backend)
        be.run_narrator(wav_path, out_dir)
        print("Done.")
        return

    # ---- Character mode ----
    campaign = args.arg1
    character = args.arg2
    if not character:
        print("Error: provide character slug")
        sys.exit(1)

    backend = args.backend or get_backend(campaign)
    print(f"Backend: {backend}")

    out_dir = os.path.join("website", campaign, "audio", "introductions")
    os.makedirs(out_dir, exist_ok=True)

    wav_path = args.wav
    if not wav_path:
        candidates = sorted(glob.glob(os.path.join(out_dir, f"{character}_audition_*.wav")))
        if not candidates:
            print(f"Error: no audition files found for {character} and no --wav specified")
            sys.exit(1)
        wav_path = candidates[0]
        print(f"No --wav specified, using: {wav_path}")

    if not os.path.exists(wav_path):
        print(f"Error: file not found: {wav_path}")
        sys.exit(1)

    be = load_backend(backend)
    be.run(campaign, character, wav_path, out_dir)

    # Clean up audition files
    audition_files = glob.glob(os.path.join(out_dir, f"{character}_audition_*.wav"))
    for f in audition_files:
        os.remove(f)
        print(f"Removed: {f}")

    update_index(out_dir)
    print("Done.")


if __name__ == "__main__":
    main()
