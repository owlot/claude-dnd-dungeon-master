#!/usr/bin/env python3
"""
Generate narrator audition samples using Qwen3-TTS VoiceDesign.
Called by tools/audition-narrator.py — do not run directly.
"""

import os
import torch
import soundfile as sf

TEXT = (
    "The city of Waterdeep never truly sleeps. Even in the hours before dawn, "
    "when the last taverns have shuttered and the watch patrols echo alone through "
    "the cobbled streets, something is always moving in the dark. "
    "Tonight, three people sat around a table in a manor that smelled of sawdust and old timber, "
    "and made the kind of plans that tend to change everything."
)
INSTRUCT = (
    "A deep British male narrator with gravitas and warmth. "
    "Slightly faster than average pace, authoritative and confident — the voice of a master storyteller "
    "reading a dark fantasy novel aloud. Rich baritone, clear diction, brisk but never rushed."
)


def run(count, voices_dir):
    from qwen_tts import Qwen3TTSModel
    print("Loading Qwen3 VoiceDesign model...")
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        device_map="cuda",
        dtype=torch.float16,
    )

    print(f"Generating {count} narrator audition samples...\n")
    for i in range(count):
        wavs, sr = model.generate_voice_design(text=TEXT, language="English", instruct=INSTRUCT)
        out_path = os.path.join(voices_dir, f"narrator_audition_{i+1}.wav")
        sf.write(out_path, wavs[0], sr)
        print(f"  [{i+1}/{count}] {out_path} ({len(wavs[0])/sr:.1f}s)")
