#!/usr/bin/env python3
"""
Qwen3-TTS backend for audio generation.
Called by tools/generate-audio.py — do not run directly.
"""

import os
import re
import torch
import numpy as np
import soundfile as sf

SAMPLE_RATE = 24000

CLONE_GEN_KWARGS = dict(
    max_new_tokens=800,     # ~30s of audio — prevents hallucination runaway
    do_sample=True,
    top_k=50,
    top_p=0.95,
    temperature=0.9,
    repetition_penalty=1.3,
    subtalker_dosample=True,
    subtalker_top_k=50,
    subtalker_top_p=0.95,
    subtalker_temperature=0.9,
)

_PHONETIC_SUBSTITUTIONS = {}


def _load_phonetic_substitutions(campaign):
    import json
    global _PHONETIC_SUBSTITUTIONS
    path = os.path.join("campaigns", campaign, "party", "phonetic-substitutions.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _PHONETIC_SUBSTITUTIONS = {rf"\b{re.escape(k)}\b": v for k, v in data.items()}
    print(f"Loaded {len(_PHONETIC_SUBSTITUTIONS)} phonetic substitutions.")


def apply_substitutions(text):
    for pattern, replacement in _PHONETIC_SUBSTITUTIONS.items():
        def _replace(m, r=replacement):
            return r if m.group(0)[0].isupper() else r[0].lower() + r[1:]
        text = re.sub(pattern, _replace, text, flags=re.IGNORECASE)
    return text.replace("—", ",")


def load_voices(campaign):
    """Load .pt voice clone prompts and phonetic substitutions. Returns {slug: prompt}."""
    _load_phonetic_substitutions(campaign)
    prompts = {}

    global_dir = os.path.join("website", "audio", "introductions")
    if os.path.exists(global_dir):
        for filename in os.listdir(global_dir):
            if filename.endswith(".pt"):
                slug = filename[:-3]
                prompts[slug] = torch.load(os.path.join(global_dir, filename), weights_only=False)

    campaign_dir = os.path.join("website", campaign, "audio", "introductions")
    if os.path.exists(campaign_dir):
        for filename in os.listdir(campaign_dir):
            if filename.endswith(".pt"):
                slug = filename[:-3]
                prompts[slug] = torch.load(os.path.join(campaign_dir, filename), weights_only=False)

    if prompts:
        print(f"Loaded voice prompts: {', '.join(sorted(prompts))}")
    else:
        print("Warning: no .pt voice prompts found. Run tools/lock-voice.py first.")
    return prompts


def load_model(voices):
    from qwen_tts import Qwen3TTSModel
    import transformers.tokenization_utils_base as _tub
    # Prevent a live HuggingFace API call during tokenizer init — model is local.
    _tub.is_base_mistral = lambda *a, **kw: False
    print("Loading Qwen3 Base (clone) model...")
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        device_map="cuda",
        dtype=torch.float16,
    )
    print("Model loaded.")
    return model


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
    return "narrator"


def generate_segment(model, voices, speaker_slug, text, overrides=None):
    text = apply_substitutions(text)
    resolved = resolve_voice(voices, speaker_slug, overrides)
    try:
        if resolved in voices:
            wavs, sr = model.generate_voice_clone(
                text=text,
                language="English",
                voice_clone_prompt=voices[resolved],
                **CLONE_GEN_KWARGS,
            )
        else:
            print(f"  Warning: no voice for [{resolved}], skipping")
            return None
        return wavs[0]
    except Exception as e:
        print(f"  Warning: failed [{speaker_slug or 'narrator'}]: {e}")
        return None


def assemble_audio(chunks):
    silence_lead  = np.zeros(int(SAMPLE_RATE * 1.0))
    silence_short = np.zeros(int(SAMPLE_RATE * 0.3))
    silence_long  = np.zeros(int(SAMPLE_RATE * 0.6))
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


def generate_scene_audio(model, voices, segments, overrides=None):
    chunks = []
    for speaker, text in segments:
        label = speaker or "narrator"
        print(f"    [{label}]: {text[:60]}{'...' if len(text) > 60 else ''}")
        audio = generate_segment(model, voices, speaker, text, overrides)
        chunks.append((speaker is not None, audio))
    return assemble_audio(chunks)


def generate_memoir_audio(model, voices, character_slug, segments, overrides=None):
    silence_lead  = np.zeros(int(SAMPLE_RATE * 1.0))
    silence_inter = np.zeros(int(SAMPLE_RATE * 0.4))
    resolved = resolve_voice(voices, character_slug, overrides)

    for block_type, text in segments:
        print(f"      [{block_type}]: {text[:60]}{'...' if len(text) > 60 else ''}")

    all_chunks = [silence_lead]
    for block_type, text in segments:
        audio = generate_segment(model, voices, resolved, text, overrides)
        if audio is not None:
            if len(all_chunks) > 1:
                all_chunks.append(silence_inter)
            all_chunks.append(audio)

    return np.concatenate(all_chunks) if len(all_chunks) > 1 else None


def audio_to_mp3(audio, path):
    wav_path = path.replace(".mp3", ".wav")
    sf.write(wav_path, audio, SAMPLE_RATE)
    ret = os.system(f'ffmpeg -y -i "{wav_path}" -q:a 2 "{path}" 2>/dev/null')
    if ret == 0:
        os.remove(wav_path)
        return path
    print(f"  ffmpeg not found, keeping WAV: {wav_path}")
    return wav_path
