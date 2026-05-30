#!/usr/bin/env python3
"""
Test phonetic substitution for a name by generating a short audio clip.

Usage:
    python tools/test-phonetic.py <campaign> <canonical-name> <phonetic>

Example:
    python tools/test-phonetic.py waterdeep-dragon-heist Lylnyler lilniyler

Generates: tools/test-phonetic-output.mp3
"""

import sys
import os
import re
import json
import unicodedata

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(TOOLS_DIR, "..", ".."))
sys.path.insert(0, TOOLS_DIR)


def get_backend(campaign):
    config_path = os.path.join(PROJECT_ROOT, "website", "assets", "config.json")
    config = json.loads(open(config_path).read())
    return config["ttsBackend"]


def load_phonetics(campaign):
    path = os.path.join(PROJECT_ROOT, "campaigns", campaign, "party", "phonetic-substitutions.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def apply_phonetics(text, phonetics):
    for canonical, phonetic in phonetics.items():
        def _replace(m, r=phonetic):
            return r if m.group(0)[0].isupper() else r[0].lower() + r[1:]
        text = re.sub(rf"\b{re.escape(canonical)}\b", _replace, text, flags=re.IGNORECASE)
    return text


def main():
    if len(sys.argv) < 4:
        print("Usage: python tools/test-phonetic.py <campaign> <canonical-name> <phonetic>")
        print("Example: python tools/test-phonetic.py waterdeep-dragon-heist Lylnyler lilniyler")
        sys.exit(1)

    campaign = sys.argv[1]
    canonical = sys.argv[2]
    phonetic = sys.argv[3]

    # Build test sentences with the canonical name in start, middle, end positions
    sentences = [
        f"{canonical} stepped forward and placed his hand on the door.",
        f"The blast came from nowhere — {canonical} had moved before any of them saw him go.",
        f"The cup on the bar slid forward, slow and deliberate, and stopped in front of {canonical}.",
    ]

    # Apply the test substitution on top of existing phonetics
    phonetics = load_phonetics(campaign)
    phonetics[canonical] = phonetic  # override for this test

    segments = []
    for sentence in sentences:
        subbed = apply_phonetics(sentence, phonetics)
        segments.append((None, subbed))
        print(f"  {sentence}")
        print(f"  → {subbed}")
        print()

    backend_name = get_backend(campaign)
    backend_path = os.path.join(TOOLS_DIR, "backends", backend_name, "generate-audio.py")
    if not os.path.exists(backend_path):
        print(f"Backend not found: {backend_path}")
        sys.exit(1)

    import importlib.util
    spec = importlib.util.spec_from_file_location("backend", backend_path)
    be = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(be)

    voices_dir = os.path.join(PROJECT_ROOT, "website", campaign, "audio", "voices")
    voices = be.load_voices(voices_dir)
    model = be.load_model(voices)

    voice_overrides_path = os.path.join(PROJECT_ROOT, "campaigns", campaign, "voice-overrides.json")
    overrides = {}
    if os.path.exists(voice_overrides_path):
        with open(voice_overrides_path) as f:
            overrides = json.load(f)

    print(f"Generating audio for '{canonical}' → '{phonetic}'...")
    audio = be.generate_scene_audio(model, voices, segments, overrides=overrides)

    if audio is None:
        print("No audio generated.")
        sys.exit(1)

    out_path = os.path.join(TOOLS_DIR, "test-phonetic-output.mp3")
    wav_path = os.path.join(TOOLS_DIR, "test-phonetic-output.wav")

    import soundfile as sf
    sf.write(wav_path, audio, be.SAMPLE_RATE)
    ret = os.system(f'ffmpeg -y -i "{wav_path}" -q:a 2 "{out_path}" 2>/dev/null')
    if ret == 0:
        os.remove(wav_path)
    else:
        out_path = wav_path
        print("ffmpeg not found, keeping WAV")

    duration = len(audio) / be.SAMPLE_RATE
    print(f"Done — {duration:.1f}s → {out_path}")

    for player, flags in [
        ("mpv", "--no-video --really-quiet"),
        ("paplay", ""),
        ("ffplay", "-nodisp -autoexit -loglevel quiet"),
        ("aplay", ""),
    ]:
        if os.system(f"which {player} >/dev/null 2>&1") == 0:
            os.system(f"{player} {flags} \"{out_path}\"")
            break


if __name__ == "__main__":
    main()
