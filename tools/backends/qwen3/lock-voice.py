#!/usr/bin/env python3
"""
Lock a character voice using Qwen3-TTS Base (ICL clone prompt).
Called by tools/lock-voice.py — do not run directly.

Produces:
  <character>.wav  — reference audio clip
  <character>.pt   — ICL voice clone prompt for generate-audio.py
"""

import re
import os
import torch
import soundfile as sf


def parse_introduction(campaign, character):
    base_slug = re.sub(r'-\d+$', '', character)

    # Search order: info/npcs/, party/characters/, info/introductions/
    for path in [
        os.path.join("campaigns", campaign, "info", "npcs", f"{character}.md"),
        os.path.join("campaigns", campaign, "party", "characters", f"{character}.md"),
        os.path.join("campaigns", campaign, "info", "introductions", f"{character}.md"),
        os.path.join("campaigns", campaign, "info", "introductions", f"{base_slug}.md"),
    ]:
        if os.path.exists(path):
            break
    else:
        return None, None, None

    with open(path, encoding="utf-8") as f:
        content = f.read()

    def get_field(text, key):
        m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        return m.group(1).strip() if m else ""

    def extract_section(sec):
        m = re.search(rf"^## {sec}\s*\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    # New unified format
    if re.search(r"^## character", content, re.MULTILINE):
        char_section = extract_section("character")
        voice_section = extract_section("voice")
        gender = get_field(char_section, "gender")
        age = get_field(char_section, "age")

        instruction_override = get_field(voice_section, "instruction").strip('"\'')
        if instruction_override:
            instruct = instruction_override
        else:
            parts = []
            if gender and age:
                parts.append(f"{gender}, {age} years old")
            elif gender:
                parts.append(gender)
            elif age:
                parts.append(f"{age} years old")
            for field in ["pitch", "pace", "tone", "quality", "notes"]:
                v = get_field(voice_section, field)
                if v:
                    parts.append(v.rstrip("."))
            instruct = ". ".join(parts) + "."

        # Body text = non-key lines in voice section
        body_lines = []
        in_body = False
        for line in voice_section.splitlines():
            if re.match(r"^\w[\w-]*:\s", line) or re.match(r'^instruction:\s*"', line):
                in_body = False
            elif line.strip() == "" and not in_body:
                continue
            else:
                in_body = True
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
        ref_text = body if body and not body.startswith("[") else None
        return instruct, ref_text, body

    return None, None, None


def run_narrator(wav_path, out_dir):
    from qwen_tts import Qwen3TTSModel
    audio, sr = sf.read(wav_path)

    print("Loading Qwen3 Base model...")
    base = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-Base", device_map="cuda", dtype=torch.float16
    )

    print("Building narrator prompt (x_vector_only_mode)...")
    prompt = base.create_voice_clone_prompt(ref_audio=(audio, sr), x_vector_only_mode=True)

    import shutil
    out_wav = os.path.join(out_dir, "narrator.wav")
    if os.path.abspath(wav_path) != os.path.abspath(out_wav):
        shutil.copy(wav_path, out_wav)
    torch.save(prompt, os.path.join(out_dir, "narrator.pt"))
    print(f"Saved: {out_dir}/narrator.wav")
    print(f"Saved: {out_dir}/narrator.pt")


def run(campaign, character, wav_path, out_dir):
    from qwen_tts import Qwen3TTSModel

    instruct, ref_text, full_text = parse_introduction(campaign, character)

    if wav_path:
        # Use provided WAV directly
        audio, sr = sf.read(wav_path)
        ref_text = ref_text or (full_text[:300] if full_text else None)
        out_wav = os.path.join(out_dir, f"{character}.wav")
        import shutil
        if os.path.abspath(wav_path) != os.path.abspath(out_wav):
            shutil.copy(wav_path, out_wav)
    elif instruct and ref_text:
        # Generate reference clip via VoiceDesign
        print("Loading Qwen3 VoiceDesign model...")
        design = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", device_map="cuda", dtype=torch.float16
        )
        print(f"Generating reference clip for {character}...")
        wavs, sr = design.generate_voice_design(text=ref_text, language="English", instruct=instruct)
        audio = wavs[0]
        out_wav = os.path.join(out_dir, f"{character}.wav")
        sf.write(out_wav, audio, sr)
        print(f"  Reference clip: {out_wav}")
        del design
        import torch as _torch
        _torch.cuda.empty_cache()
    else:
        print(f"Error: no introduction file found for {character} and no --wav provided")
        raise SystemExit(1)

    print("Loading Qwen3 Base model...")
    base = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-Base", device_map="cuda", dtype=torch.float16
    )

    if ref_text:
        print(f"Building ICL clone prompt (ref_text: '{ref_text[:60]}...')")
        prompt = base.create_voice_clone_prompt(ref_audio=(audio, sr), ref_text=ref_text)
    else:
        print("Building ICL clone prompt (x_vector_only_mode — no ref_text)")
        prompt = base.create_voice_clone_prompt(ref_audio=(audio, sr), x_vector_only_mode=True)

    out_pt = os.path.join(out_dir, f"{character}.pt")
    torch.save(prompt, out_pt)
    print(f"Saved: {out_wav}")
    print(f"Saved: {out_pt}")
