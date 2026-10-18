#!/usr/bin/env python3
"""
Narrator audition samples through a tts-serve server (voice design: needs VoxCPM2).
Called by tools/audition-narrator.py (--backend tts-serve): do not run directly.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soundfile as sf
from ttsserve_client import Client, TTSServeError
from ttsserve_common import clip_to_array, design_prefix

# Same text and description as the qwen3 backend, so the two engines can be compared directly.
TEXT = (
    "The city of Waterdeep never truly sleeps. Even in the hours before dawn, "
    "when the last taverns have shuttered and the watch patrols echo alone through "
    "the cobbled streets, something is always moving in the dark. "
    "Tonight, three people sat around a table in a manor that smelled of sawdust and old timber, "
    "and made the kind of plans that tend to change everything."
)
INSTRUCT = (
    "A deep British male narrator with gravitas and warmth. "
    "Slightly faster than average pace, authoritative and confident, the voice of a master storyteller "
    "reading a dark fantasy novel aloud. Rich baritone, clear diction, brisk but never rushed."
)


def run(count, voices_dir):
    client = Client()
    print(f"Server: {client.url}  {client.check()}")
    print(f"Generating {count} narrator audition samples...\n")
    for i in range(1, count + 1):
        try:
            clip = client.synthesize(f"{design_prefix(INSTRUCT)}{TEXT}", seed=random.randint(1, 1000))
        except TTSServeError as exc:
            raise SystemExit(f"Error: {exc}")
        audio = clip_to_array(clip, None)
        out_path = os.path.join(voices_dir, f"narrator_audition_{i}.wav")
        sf.write(out_path, audio, clip.sample_rate)
        print(f"  [{i}/{count}] {out_path} ({len(audio) / clip.sample_rate:.1f}s, seed {clip.seed})")
