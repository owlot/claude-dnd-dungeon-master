#!/usr/bin/env python3
"""
tts-serve backend for audio generation: each segment is one POST /synthesize to a tts-serve server, cloning
from the locked reference WAV and its transcript. Works with any engine that clones (Qwen3-TTS, VoxCPM2, ...).
Called by tools/generate-audio.py (--backend tts-serve): do not run directly.

Differences from the local qwen3 backend: the server picks the sampling settings (set engine parameters under
`ttsServe.params` in website/assets/config.json), the reference clip is re-encoded on every request, and long
text is split into sentence chunks here (ttsServe.maxChunkChars, default 400) because the server has no
max_new_tokens guard. ttsServe.rawText=true skips the phonetic substitutions and the em-dash rewrite. Clips are resampled
to 24 kHz and level-normalised per chunk, so scenes and memoirs match the other backends and no voice is louder.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from ttsserve_client import Client, TTSServeError
from ttsserve_common import (SAMPLE_RATE, audition_text, clip_to_array, find_character_file, normalize,
                             parse_introduction, phonetic_subs, sentence_chunks, setting, sidecar, trim_silence, MAX_CHUNK_CHARS)

_SUBS = {}


def _load_phonetic_substitutions(campaign):
    global _SUBS
    _SUBS = phonetic_subs(campaign)
    if _SUBS:
        print(f"Loaded {len(_SUBS)} phonetic substitutions.")


def apply_substitutions(text):
    if setting("rawText", False):  # ttsServe.rawText: send the story text as written (no respelling, em dashes kept)
        return text
    for pattern, replacement in _SUBS.items():
        def _replace(m, r=replacement):
            return r if m.group(0)[0].isupper() else r[0].lower() + r[1:]
        text = re.sub(pattern, _replace, text, flags=re.IGNORECASE)
    return text.replace("—", ",")


def _transcript(campaign, slug):
    """Intro text the locked clip was spoken from, or None (narrator, generic voices)."""
    path = find_character_file(campaign, slug)
    if not path:
        return None
    try:
        body = parse_introduction(path)[2]
    except SystemExit:
        return None
    return audition_text(campaign, body) or None


def load_voices(campaign):
    """{slug: {"wav": path, "transcript": text or None}} from the campaign folder over the global one."""
    _load_phonetic_substitutions(campaign)
    voices = {}
    for folder, scoped in ((os.path.join("website", "audio", "introductions"), False),
                           (os.path.join("website", campaign, "audio", "introductions"), True)):
        if not os.path.isdir(folder):
            continue
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith(".wav") or "_audition_" in filename or "_ref" in filename:
                continue
            slug = filename[:-4]
            wav = os.path.join(folder, filename)
            voices[slug] = {"wav": wav, "transcript": (sidecar(wav) or _transcript(campaign, slug)) if scoped else None}
    if voices:
        print(f"Loaded voices: {', '.join(sorted(voices))}")
    else:
        print("Warning: no locked voices found. Run tools/audition-voice.py and tools/lock-voice.py first.")
    return voices


def load_model(voices):
    client = Client()
    print(f"tts-serve at {client.url}: {client.check()}")
    return client


def resolve_voice(voices, speaker_slug, overrides=None):
    if speaker_slug and speaker_slug in voices:
        return speaker_slug
    if overrides and speaker_slug in overrides:
        mapped = overrides[speaker_slug]
        if mapped in voices:
            return mapped
    if speaker_slug:
        for key in voices:
            if key.startswith(speaker_slug + "-"):
                return key
    if overrides and "narrator" in overrides:
        mapped = overrides["narrator"]
        if mapped in voices:
            return mapped
    return "narrator"


def generate_segment(client, voices, speaker_slug, text, overrides=None):
    resolved = resolve_voice(voices, speaker_slug, overrides)
    if resolved not in voices:
        print(f"  Warning: no voice for [{resolved}], skipping")
        return None
    voice, parts = voices[resolved], []
    gap = np.zeros(int(SAMPLE_RATE * 0.1), dtype="float32")
    try:
        for chunk in sentence_chunks(apply_substitutions(text), int(setting("maxChunkChars", MAX_CHUNK_CHARS))):
            clip = client.synthesize(chunk, ref_wav=voice["wav"], ref_text=voice["transcript"])
            if parts:
                parts.append(gap)
            # cut the dead air some engines start a clone with, then give every voice and chunk the same level
            parts.append(normalize(trim_silence(clip_to_array(clip), SAMPLE_RATE), SAMPLE_RATE))
    except TTSServeError as exc:
        print(f"  Warning: failed [{speaker_slug or 'narrator'}]: {exc}")
        return None
    return np.concatenate(parts) if parts else None


def assemble_audio(chunks):
    silence_lead = np.zeros(int(SAMPLE_RATE * 1.0))
    silence_short = np.zeros(int(SAMPLE_RATE * 0.3))
    silence_long = np.zeros(int(SAMPLE_RATE * 0.6))
    all_chunks = [silence_lead]
    prev_dialogue = False
    for is_dialogue, audio in chunks:
        if audio is None:
            continue
        if len(all_chunks) > 1:
            all_chunks.append(silence_long if (prev_dialogue and not is_dialogue) else silence_short)
        all_chunks.append(audio)
        prev_dialogue = is_dialogue
    return np.concatenate(all_chunks) if len(all_chunks) > 1 else None


def generate_scene_audio(client, voices, segments, overrides=None):
    chunks = []
    for speaker, text in segments:
        print(f"    [{speaker or 'narrator'}]: {text[:60]}{'...' if len(text) > 60 else ''}")
        chunks.append((speaker is not None, generate_segment(client, voices, speaker, text, overrides)))
    return assemble_audio(chunks)


def generate_memoir_audio(client, voices, character_slug, segments, overrides=None):
    silence_lead = np.zeros(int(SAMPLE_RATE * 1.0))
    silence_inter = np.zeros(int(SAMPLE_RATE * 0.4))
    resolved = resolve_voice(voices, character_slug, overrides)
    all_chunks = [silence_lead]
    for block_type, text in segments:
        print(f"      [{block_type}]: {text[:60]}{'...' if len(text) > 60 else ''}")
        audio = generate_segment(client, voices, resolved, text, overrides)
        if audio is not None:
            if len(all_chunks) > 1:
                all_chunks.append(silence_inter)
            all_chunks.append(audio)
    return np.concatenate(all_chunks) if len(all_chunks) > 1 else None
