#!/usr/bin/env python3
"""
Generate 4 voice audition samples for a character using MOSS-VoiceGenerator.

Voice is created from scratch using the character's introduction frontmatter
as the instruction — no reference audio needed.

Usage:
    python tools/audition-voice.py <campaign-slug> <character-slug>
    python tools/audition-voice.py waterdeep-dragon-heist yagra-stonefist

    # Generate more samples:
    python tools/audition-voice.py waterdeep-dragon-heist yagra-stonefist --count 6

Output:
    website/<campaign>/audio/voices/<character>_audition_1.wav
    ...

After listening, lock in a choice with:
    python tools/lock-voice.py <campaign-slug> <character-slug> --wav <chosen_audition.wav>
    (this renders the introduction text with MOSS-TTS using the chosen WAV as reference)
"""

import re
import sys
import os
import argparse
import gc
import time
import numpy as np
import soundfile as sf
import torch


SAMPLE_RATE = 24000

# MOSS-VoiceGenerator recommended decoding settings
GEN_KWARGS = dict(
    max_new_tokens=4096,
    audio_temperature=1.5,
    audio_top_p=0.6,
    audio_top_k=50,
    audio_repetition_penalty=1.1,
)


def parse_introduction(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not fm_match:
        print(f"Error: could not parse frontmatter in {path}")
        sys.exit(1)

    frontmatter = fm_match.group(1)
    body = fm_match.group(2).strip()

    def get_field(key):
        m = re.search(rf"^\s+{key}:\s*(.+)$", frontmatter, re.MULTILINE)
        return m.group(1).strip() if m else ""

    name_m = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else "Unknown"

    gender_m = re.search(r"^gender:\s*(.+)$", frontmatter, re.MULTILINE)
    gender = gender_m.group(1).strip() if gender_m else ""

    age_m = re.search(r"^age:\s*(.+)$", frontmatter, re.MULTILINE)
    age = age_m.group(1).strip() if age_m else ""

    pitch   = get_field("pitch")
    pace    = get_field("pace")
    tone    = get_field("tone")
    quality = get_field("quality")
    notes   = get_field("notes")
    instruction_override = get_field("instruction").strip('"\'')

    if instruction_override:
        # Use the explicit instruction field if present — best results
        instruction = instruction_override
    else:
        # Auto-build from structured fields as fallback
        parts = []
        header = []
        if gender and age:
            header.append(f"{gender}, {age}")
        elif gender:
            header.append(gender)
        if pitch:
            header.append(pitch)
        if header:
            parts.append(", ".join(header))

        middle = []
        if pace:
            middle.append(pace)
        if tone:
            middle.append(tone)
        if middle:
            parts.append(", ".join(middle))

        if quality:
            parts.append(quality)
        if notes:
            parts.append(notes)

        instruction = ". ".join(p.rstrip(".") for p in parts if p) + "."

    return name, instruction, body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", help="Campaign slug (e.g. waterdeep-dragon-heist)")
    parser.add_argument("character", help="Character slug (e.g. yagra-stonefist)")
    parser.add_argument("--count", type=int, default=4, help="Number of samples to generate (default: 4)")
    args = parser.parse_args()

    intro_path = os.path.join("campaigns", args.campaign, "info", "introductions", f"{args.character}.md")
    if not os.path.exists(intro_path):
        print(f"Error: introduction file not found: {intro_path}")
        sys.exit(1)

    voices_dir = os.path.join("website", args.campaign, "audio", "introductions")
    os.makedirs(voices_dir, exist_ok=True)

    name, instruction, text = parse_introduction(intro_path)

    print(f"Character:   {name}")
    print(f"Instruction: {instruction}")
    print(f"Text:        {text[:80]}...")
    print()

    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)

    import transformers.modeling_utils as _mu
    _mu.caching_allocator_warmup = lambda *a, **kw: None

    from transformers import AutoModel, AutoProcessor
    print("Loading MOSS-VoiceGenerator...")
    processor = AutoProcessor.from_pretrained(
        "OpenMOSS-Team/MOSS-VoiceGenerator",
        trust_remote_code=True,
        normalize_inputs=True,
    )
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model = AutoModel.from_pretrained(
        "OpenMOSS-Team/MOSS-VoiceGenerator",
        trust_remote_code=True,
        dtype=dtype,
        device_map="auto" if torch.cuda.is_available() else None,
    )
    if not torch.cuda.is_available():
        model = model.to("cpu")
    model.eval()
    print(f"Model loaded. Generating {args.count} samples...\n")

    device = "cuda" if torch.cuda.is_available() else "cpu"

    for i in range(1, args.count + 1):
        conversations = [[processor.build_user_message(text=text, instruction=instruction)]]
        batch = processor(conversations=conversations, mode="generation")
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)

        t0 = time.time()
        with torch.no_grad():
            output_ids = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                **GEN_KWARGS,
            )

        messages = processor.decode(output_ids)
        if not messages[0].audio_codes_list:
            print(f"  [{i}/{args.count}] Warning: model returned no audio")
            continue

        audio = messages[0].audio_codes_list[0]
        audio_np = audio.detach().float().cpu().numpy() if isinstance(audio, torch.Tensor) else np.asarray(audio, dtype=np.float32)
        if audio_np.ndim > 1:
            audio_np = audio_np.reshape(-1)

        out_path = os.path.join(voices_dir, f"{args.character}_audition_{i}.wav")
        sf.write(out_path, audio_np, SAMPLE_RATE)
        duration = len(audio_np) / SAMPLE_RATE
        print(f"  [{i}/{args.count}] {out_path} ({duration:.1f}s in {time.time()-t0:.1f}s)")

        del batch, input_ids, attention_mask, output_ids, messages
        torch.cuda.empty_cache()

    del model, processor
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print(f"\nDone. Listen and pick the best one, then lock it in with:")
    print(f"  python tools/lock-voice.py {args.campaign} {args.character} --wav <chosen_audition.wav>")


if __name__ == "__main__":
    main()
