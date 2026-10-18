#!/usr/bin/env python3
"""
Voice audition samples through a tts-serve server.
Called by tools/audition-voice.py (--backend tts-serve): do not run directly.

Voice design needs an engine that supports it (VoxCPM2): the description goes in parentheses before the
text and no reference audio is sent. Per-character settings live in the ## voice section of the NPC/PC file:
    design:       description used instead of the long `instruction:`/pitch/pace fields (short and depth-first works best)
    design_text:  the exact words spoken for design (default: the first sentences of the intro). The voice depends on
                  the text as well as the seed, so keep design_text fixed to re-find a voice
    design_seed:  take 1 uses this seed exactly, take N uses seed+N-1 (so a voice you like can be re-found)
    design_cfg:   guidance, default 3.0
Each take is trimmed, level-normalised and saved with a <slug>_audition_N.txt holding the exact spoken text, which
lock-voice turns into the transcript. --reaudition clones the locked WAV (works on any cloning engine).
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import soundfile as sf
from ttsserve_client import Client, TTSServeError
from ttsserve_common import (DESIGN_CFG, audition_text, clip_to_array, design_excerpt, design_prefix,
                             find_character_file, normalize, parse_introduction, pause_text, sidecar,
                             trim_and_fade, voice_fields)


def _character(campaign, character):
    path = find_character_file(campaign, character)
    if not path:
        raise SystemExit(f"Error: character file not found for {character}")
    return path, parse_introduction(path)


def _write(audio, sr, voices_dir, character, i, count, clip, text=None):
    out_path = os.path.join(voices_dir, f"{character}_audition_{i}.wav")
    sf.write(out_path, np.concatenate([np.zeros(int(sr * 0.2), dtype="float32"), audio]), sr)
    if text:
        with open(os.path.splitext(out_path)[0] + ".txt", "w", encoding="utf-8") as f:
            f.write(text + "\n")
    rtf = f", rtf {clip.rtf:.2f}" if isinstance(clip.rtf, (int, float)) else ""
    print(f"  [{i}/{count}] {out_path} ({len(audio) / sr:.1f}s, seed {clip.seed}{rtf})")


def run(campaign, character, count, voices_dir):
    path, (name, instruct, body) = _character(campaign, character)
    fields = voice_fields(path)
    description = fields["design"] or instruct
    cfg = float(fields["design_cfg"] or DESIGN_CFG)
    base_seed = int(fields["design_seed"]) if fields["design_seed"] else None
    text = pause_text(audition_text(campaign, fields["design_text"]) if fields["design_text"]
                      else design_excerpt(audition_text(campaign, body)))
    client = Client()
    print(f"Server:      {client.url}  {client.check()}")
    print(f"Character:   {name}\nDescription: {description}\nText:        {text[:90]}...")
    print(f"Settings:    cfg {cfg}, seed {'from ' + str(base_seed) if base_seed else 'random'}\n")
    print(f"Generating {count} audition samples...\n")
    for i in range(1, count + 1):
        seed = ((base_seed - 1 + i - 1) % 1000) + 1 if base_seed else random.randint(1, 1000)
        try:
            clip = client.synthesize(f"{design_prefix(description)}{text}", seed=seed, cfg_value=cfg)
        except TTSServeError as exc:
            raise SystemExit(f"Error: {exc}")
        audio = normalize(trim_and_fade(clip_to_array(clip, None), clip.sample_rate), clip.sample_rate)
        _write(audio, clip.sample_rate, voices_dir, character, i, count, clip, text)


def run_reaudition(campaign, character, count, voices_dir, wav_path):
    _, (name, _, body) = _character(campaign, character)
    text = audition_text(campaign, body)
    if not os.path.exists(wav_path):
        raise SystemExit(f"Error: locked voice {wav_path} not found")
    transcript = sidecar(wav_path) or text  # the locked clip's own transcript if saved, else the intro text
    client = Client()
    print(f"Server:      {client.url}  {client.check()}")
    print(f"Character:   {name}\nReference:   {wav_path}\nText:        {text[:80]}...\n")
    print(f"Generating {count} re-audition samples...\n")
    for i in range(1, count + 1):
        try:
            clip = client.synthesize(text, ref_wav=wav_path, ref_text=transcript, seed=random.randint(1, 1000))
        except TTSServeError as exc:
            raise SystemExit(f"Error: {exc}")
        audio = normalize(trim_and_fade(clip_to_array(clip, None), clip.sample_rate), clip.sample_rate)
        _write(audio, clip.sample_rate, voices_dir, character, i, count, clip)
