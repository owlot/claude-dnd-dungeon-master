#!/usr/bin/env python3
"""
Generate voice audition samples using Qwen3-TTS VoiceDesign.
Called by tools/audition-voice.py — do not run directly.
"""

import re
import os
import argparse
import torch
import soundfile as sf


def _build_instruct(fields, gender="", age=""):
    """Build TTS instruction string from voice fields."""
    instruction_override = fields.get("instruction", "").strip('"\'')
    if instruction_override:
        return instruction_override
    parts = []
    if gender and age:
        parts.append(f"{gender}, {age} years old")
    elif gender:
        parts.append(gender)
    elif age:
        parts.append(f"{age} years old")
    for field in ["pitch", "pace", "tone", "quality", "notes"]:
        v = fields.get(field, "")
        if v:
            parts.append(v.rstrip("."))
    return ". ".join(parts) + "."


def _extract_section(content, section):
    """Extract content of a ## section from a unified NPC/PC file."""
    m = re.search(rf"^## {section}\s*\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def parse_introduction(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    # New unified format (## sections)
    if re.search(r"^## character", content, re.MULTILINE):
        char_section = _extract_section(content, "character")
        voice_section = _extract_section(content, "voice")

        def get_field(section_text, key):
            m = re.search(rf"^{key}:\s*(.+)$", section_text, re.MULTILINE)
            return m.group(1).strip() if m else ""

        name = get_field(char_section, "name") or "Unknown"
        gender = get_field(char_section, "gender")
        age = get_field(char_section, "age")

        fields = {}
        for field in ["pitch", "pace", "tone", "quality", "notes", "instruction"]:
            fields[field] = get_field(voice_section, field)

        # Body text is everything after the key: value lines
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

        instruct = _build_instruct(fields, gender, age)
        return name, instruct, body

    print(f"Error: could not parse {path} — expected ## character section")
    raise SystemExit(1)


def run(campaign, character, count, voices_dir):
    # Search order: info/npcs/, party/characters/, info/introductions/ (generic templates)
    for intro_path in [
        os.path.join("campaigns", campaign, "info", "npcs", f"{character}.md"),
        os.path.join("campaigns", campaign, "party", "characters", f"{character}.md"),
        os.path.join("campaigns", campaign, "info", "introductions", f"{character}.md"),
    ]:
        if os.path.exists(intro_path):
            break
    else:
        print(f"Error: character file not found for {character}")
        raise SystemExit(1)

    name, instruct, text = parse_introduction(intro_path)

    # Apply campaign phonetic substitutions to the audition text
    import json as _json
    subs_path = os.path.join("campaigns", campaign, "party", "phonetic-substitutions.json")
    if os.path.exists(subs_path):
        subs = {rf"\b{re.escape(k)}\b": v for k, v in _json.load(open(subs_path, encoding="utf-8")).items()}
        for pattern, replacement in subs.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    print(f"Character:   {name}")
    print(f"Instruction: {instruct}")
    print(f"Text:        {text[:80]}...")
    print()

    from qwen_tts import Qwen3TTSModel
    print("Loading Qwen3 VoiceDesign model...")
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        device_map="cuda",
        dtype=torch.float16,
    )

    import numpy as np
    silence = np.zeros(int(24000 * 1.0))

    print(f"Generating {count} audition samples...\n")
    for i in range(count):
        wavs, sr = model.generate_voice_design(text=text, language="English", instruct=instruct)
        audio = np.concatenate([silence, wavs[0]])
        out_path = os.path.join(voices_dir, f"{character}_audition_{i+1}.wav")
        sf.write(out_path, audio, sr)
        print(f"  [{i+1}/{count}] {out_path} ({len(audio)/sr:.1f}s)")
