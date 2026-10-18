#!/usr/bin/env python3
"""
Lock a voice for the tts-serve backend.
Called by tools/lock-voice.py (--backend tts-serve): do not run directly.

With tts-serve the voice IS the reference WAV plus its transcript, so locking copies the chosen audition
to <slug>.wav and its <slug>_audition_N.txt (the exact text spoken) to <slug>.txt, which is the transcript
generate-audio sends with the clip (falling back to the intro text in the character file). No .pt is built.
"""
import glob
import os
import shutil

import soundfile as sf


MIN_REF_SECONDS = 2.0  # tts-serve rejects shorter reference clips


def _copy(wav_path, out_wav):
    """Copy the chosen audition as is, lead-in included (the DM wants the lead-in; the qwen3 lock copies it too)."""
    info = sf.info(wav_path)
    if info.duration < MIN_REF_SECONDS:
        raise SystemExit(f"Error: {wav_path} is {info.duration:.1f}s; tts-serve needs a reference of at least "
                         f"{MIN_REF_SECONDS:.0f}s")
    if os.path.abspath(wav_path) != os.path.abspath(out_wav):
        shutil.copy(wav_path, out_wav)
    print(f"Saved: {out_wav} ({info.duration:.1f}s, {info.samplerate} Hz)")


def run_narrator(wav_path, out_dir):
    _copy(wav_path, os.path.join(out_dir, "narrator.wav"))


def run(campaign, character, wav_path, out_dir):
    _copy(wav_path, os.path.join(out_dir, f"{character}.wav"))
    out_txt = os.path.join(out_dir, f"{character}.txt")
    src_txt = os.path.splitext(wav_path)[0] + ".txt"
    if os.path.exists(src_txt):  # exact text spoken in the audition = the clip's transcript
        shutil.copy(src_txt, out_txt)
        print(f"Saved: {out_txt}")
    else:
        if os.path.exists(out_txt):
            os.remove(out_txt)  # stale transcript from a previous voice
        print("Transcript: none saved with this clip; generate-audio falls back to the intro text in the character file.")
    for old in glob.glob(os.path.join(out_dir, f"{character}_audition_*.txt")):
        os.remove(old)
