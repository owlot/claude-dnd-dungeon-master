#!/usr/bin/env python3
"""
Rebuild all voice clone prompts using x_vector_only_mode to prevent hallucination.

Usage:
    python tools/rebuild-prompts.py waterdeep-dragon-heist
    python tools/rebuild-prompts.py narrator  # global narrator only
"""

import sys
import os
import torch
import soundfile as sf

def rebuild_dir(model, voices_dir):
    rebuilt = []
    for filename in sorted(os.listdir(voices_dir)):
        if not filename.endswith(".wav") or "_audition_" in filename:
            continue
        slug = filename[:-4]
        wav_path = os.path.join(voices_dir, filename)
        pt_path = os.path.join(voices_dir, f"{slug}.pt")

        audio, sr = sf.read(wav_path)
        duration = len(audio) / sr
        print(f"  Rebuilding: {slug} ({duration:.1f}s ref — full length)")
        prompt = model.create_voice_clone_prompt(
            ref_audio=(audio, sr),
            x_vector_only_mode=True,
        )
        torch.save(prompt, pt_path)
        rebuilt.append(slug)

    return rebuilt


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/rebuild-prompts.py <campaign-slug|narrator>")
        sys.exit(1)

    from qwen_tts import Qwen3TTSModel
    print("Loading Base model...")
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        device_map="cuda",
        dtype=torch.float16,
    )

    arg = sys.argv[1]

    if arg == "narrator":
        dirs = [os.path.join("website", "audio", "introductions")]
    else:
        dirs = [
            os.path.join("website", "audio", "introductions"),
            os.path.join("website", arg, "audio", "introductions"),
        ]

    for d in dirs:
        if not os.path.exists(d):
            print(f"Skipping (not found): {d}")
            continue
        print(f"\nRebuilding prompts in: {d}")
        rebuilt = rebuild_dir(model, d)
        print(f"  Done: {', '.join(rebuilt)}")

    print("\nAll prompts rebuilt with x_vector_only_mode.")


if __name__ == "__main__":
    main()
