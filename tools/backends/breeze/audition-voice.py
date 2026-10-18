#!/usr/bin/env python3
"""
Voice audition through Breeze TTS 2 (voice design: no reference audio).
Called by tools/audition-voice.py (--backend breeze): do not run directly.

Settings in the ## voice section of the NPC/PC file (all optional):
    design:       short voice description (depth first, 2 to 3 sentences). Default: built from pitch/pace/tone/quality/notes
    design_text:  the exact words spoken (default: the first sentences of the intro)
    design_seed:  take 1 uses this seed, take N uses seed+N-1 (Breeze seeds only repeat on the same machine)
    design_cfg:   cfg_scale, default 4 (the Breeze README's setting for instructions)
Each take is trimmed, level-normalised, gets 0.5 s of silence in front (so a Bluetooth speaker has time to wake up) and
is saved with <slug>_audition_N.txt holding the exact spoken text, which lock-voice uses as the transcript.
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tts-serve"))
import numpy as np
import soundfile as sf
from breeze_client import SAMPLE_RATE, Breeze, BreezeError
from ttsserve_common import (audition_text, design_excerpt, find_character_file, normalize, parse_introduction,
                             trim_and_fade, voice_fields)

LEAD_S = 0.5
DEFAULT_CFG = 4.0


def run(campaign, character, count, voices_dir):
    path = find_character_file(campaign, character)
    if not path:
        raise SystemExit(f"Error: character file not found for {character}")
    name, instruct, body = parse_introduction(path)
    f = voice_fields(path)
    description = f["design"] or instruct
    text = audition_text(campaign, f["design_text"]) if f["design_text"] else design_excerpt(audition_text(campaign, body))
    cfg = float(f["design_cfg"] or DEFAULT_CFG)
    base = int(f["design_seed"]) if f["design_seed"] else None
    client = Breeze()
    info = client.check()
    print(f"Server:      {client.url}  (model {str(info.get('model_digest'))[:8]}, frame rate {info.get('frame_rate')})")
    print(f"Character:   {name}\nDescription: {description}\nText:        {text}")
    print(f"Settings:    cfg_scale {cfg}, seed {'from ' + str(base) if base else 'random'}\n")
    print(f"Generating {count} audition samples...\n")
    for i in range(1, count + 1):
        seed = ((base - 1 + i - 1) % 1000) + 1 if base else random.randint(1, 1000)
        try:
            audio = client.speak(text, instruction=description, cfg_scale=cfg, seed=seed)
        except BreezeError as exc:
            raise SystemExit(f"Error: {exc}")
        audio = normalize(trim_and_fade(audio, SAMPLE_RATE), SAMPLE_RATE)
        out = os.path.join(voices_dir, f"{character}_audition_{i}.wav")
        sf.write(out, np.concatenate([np.zeros(int(SAMPLE_RATE * LEAD_S), dtype="float32"), audio]), SAMPLE_RATE)
        with open(os.path.splitext(out)[0] + ".txt", "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"  [{i}/{count}] {out} ({len(audio) / SAMPLE_RATE:.1f}s, seed {seed})")


def run_reaudition(campaign, character, count, voices_dir, wav_path):
    raise SystemExit("Error: --reaudition for the breeze backend is not built yet (clone mode); use --backend tts-serve")
