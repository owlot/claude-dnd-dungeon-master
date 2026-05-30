#!/usr/bin/env python3
"""
Lock a character voice using MOSS-TTS v1.5 (renders introduction as canonical WAV).
Called by tools/lock-voice.py — do not run directly.

Produces:
  <character>.wav  — introduction text rendered in the chosen voice
"""

import re
import os
import gc
import shutil
import numpy as np
import soundfile as sf
import torch

SAMPLE_RATE = 24000

GEN_KWARGS = dict(
    max_new_tokens=4096,
    text_temperature=0.1,
    audio_temperature=0.6,
    audio_top_p=0.8,
    audio_top_k=25,
    audio_repetition_penalty=1.3,
)


def parse_introduction(campaign, character):
    import re as _re
    base_slug = _re.sub(r'-\d+$', '', character)
    intro_path = os.path.join("campaigns", campaign, "info", "introductions", f"{character}.md")
    if not os.path.exists(intro_path):
        intro_path = os.path.join("campaigns", campaign, "info", "introductions", f"{base_slug}.md")
    if not os.path.exists(intro_path):
        return None
    with open(intro_path, encoding="utf-8") as f:
        content = f.read()
    fm_match = re.match(r"^---\n.*?\n---\n(.*)", content, re.DOTALL)
    return fm_match.group(1).strip() if fm_match else content.strip()


def run_narrator(wav_path, out_dir):
    shutil.copy(wav_path, os.path.join(out_dir, "narrator.wav"))
    print(f"Saved: {out_dir}/narrator.wav")


def run(campaign, character, wav_path, out_dir):
    text = parse_introduction(campaign, character)
    out = os.path.join(out_dir, f"{character}.wav")

    if not text:
        print(f"No introduction file found for {character} — copying WAV directly.")
        shutil.copy(wav_path, out)
        print(f"Saved: {out}")
        return

    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)

    import transformers.modeling_utils as _mu
    _mu.caching_allocator_warmup = lambda *a, **kw: None

    from transformers import AutoModel, AutoProcessor
    print("Loading MOSS-TTS v1.5...")
    processor = AutoProcessor.from_pretrained("OpenMOSS-Team/MOSS-TTS-v1.5", trust_remote_code=True)
    processor.audio_tokenizer = processor.audio_tokenizer.to("cuda")
    model = AutoModel.from_pretrained(
        "OpenMOSS-Team/MOSS-TTS-v1.5",
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()

    print(f"Rendering introduction ({len(text)} chars)...")
    conversations = [[processor.build_user_message(text=text, reference=[wav_path], language="English")]]
    inputs = processor(conversations=conversations, mode="generation", return_tensors="pt")
    inputs = {k: v.to("cuda") if hasattr(v, "to") else v for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(**inputs, **GEN_KWARGS)

    messages = processor.decode(output_ids)
    audio = messages[0].audio_codes_list[0]
    audio_np = audio.detach().float().cpu().numpy() if isinstance(audio, torch.Tensor) else np.asarray(audio, dtype=np.float32)
    if audio_np.ndim > 1:
        audio_np = audio_np.reshape(-1)

    sf.write(out, audio_np, SAMPLE_RATE)
    print(f"Saved: {out} ({len(audio_np)/SAMPLE_RATE:.1f}s)")

    del model, processor, inputs, output_ids, messages
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
