#!/usr/bin/env python3
"""
Generate N voice samples for a character using MOSS-TTS v1.5 voice cloning
from one or more reference audio files (WAV or OGG).

Use this instead of audition-voice.py when you have real reference audio
(e.g. game sound effects, existing recordings) that captures the voice
texture the model descriptions can't produce.

Usage:
    python tools/audition-voice-ref.py <campaign-slug> <character-slug> <ref1> [ref2 ...]
    python tools/audition-voice-ref.py waterdeep-dragon-heist yagra-stonefist ~/Downloads/OrcFemale01.ogg ~/Downloads/OrcFemale02.ogg

    # Override number of samples (default: 4)
    python tools/audition-voice-ref.py waterdeep-dragon-heist yagra-stonefist ref.wav --count 6

Output:
    website/<campaign>/audio/voices/<character>_audition_1.wav
    ...

After listening, lock in a choice with:
    python tools/lock-voice.py <campaign-slug> <character-slug> --wav <chosen_audition.wav>

How it works:
    - All reference files are concatenated into one clip (resampled to 24kHz)
    - MOSS-TTS v1.5 uses the clip for voice cloning via the `reference` field
    - Text comes from campaigns/<campaign>/info/introductions/<character>.md
    - Each sample is independent (different random seed) — pick the best one

Environment:
    conda activate moss-tts
    (installed at /tmp/MOSS-TTS, model cached in ~/.cache/huggingface)
"""

import re
import sys
import os
import argparse
import torch
import torchaudio
import soundfile as sf


TARGET_SR = 24000


def parse_introduction(campaign, character_slug):
    intro_path = os.path.join("campaigns", campaign, "info", "introductions", f"{character_slug}.md")
    if not os.path.exists(intro_path):
        print(f"Error: introduction file not found: {intro_path}")
        sys.exit(1)

    with open(intro_path, encoding="utf-8") as f:
        content = f.read()

    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not fm_match:
        print(f"Error: could not parse frontmatter in {intro_path}")
        sys.exit(1)

    frontmatter = fm_match.group(1)
    body = fm_match.group(2).strip()

    name_m = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    name = name_m.group(1).strip() if name_m else character_slug

    return name, body


def load_and_concat_refs(ref_paths):
    clips = []
    for path in ref_paths:
        if not os.path.exists(path):
            print(f"Error: reference file not found: {path}")
            sys.exit(1)
        # torchaudio handles both wav and ogg
        wav, sr = torchaudio.load(path)
        if wav.shape[0] > 1:
            wav = wav.mean(0, keepdim=True)
        if sr != TARGET_SR:
            wav = torchaudio.functional.resample(wav, sr, TARGET_SR)
        clips.append(wav)
    return torch.cat(clips, dim=-1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", help="Campaign slug (e.g. waterdeep-dragon-heist)")
    parser.add_argument("character", help="Character slug (e.g. yagra-stonefist)")
    parser.add_argument("refs", nargs="+", help="Reference audio files (WAV or OGG)")
    parser.add_argument("--count", type=int, default=4, help="Number of samples to generate (default: 4)")
    args = parser.parse_args()

    name, text = parse_introduction(args.campaign, args.character)

    voices_dir = os.path.join("website", args.campaign, "audio", "voices")
    os.makedirs(voices_dir, exist_ok=True)

    # Save concatenated reference as a WAV the processor can load by path
    ref_audio = load_and_concat_refs(args.refs)
    ref_wav_path = os.path.join(voices_dir, f"{args.character}_ref.wav")
    torchaudio.save(ref_wav_path, ref_audio, TARGET_SR)
    duration = ref_audio.shape[-1] / TARGET_SR
    # Free reference tensor before loading model
    del ref_audio
    import gc
    gc.collect()
    print(f"Character:  {name}")
    print(f"Reference:  {duration:.2f}s ({len(args.refs)} file(s)) → {ref_wav_path}")
    print(f"Text:       {text[:80]}...")
    print()

    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)

    import transformers.modeling_utils as _mu
    _mu.caching_allocator_warmup = lambda *a, **kw: None

    from transformers import AutoModel, AutoProcessor
    print("Loading MOSS-TTS v1.5...")
    processor = AutoProcessor.from_pretrained("OpenMOSS-Team/MOSS-TTS-v1.5", trust_remote_code=True)
    model = AutoModel.from_pretrained(
        "OpenMOSS-Team/MOSS-TTS-v1.5",
        trust_remote_code=True,
        dtype=torch.bfloat16,
    ).to("cuda")
    model.eval()
    sample_rate = int(getattr(processor.model_config, "sampling_rate", TARGET_SR))

    print(f"Generating {args.count} samples...\n")
    import time
    import numpy as np
    for i in range(1, args.count + 1):
        conversations = [[processor.build_user_message(text=text, reference=[ref_wav_path])]]
        inputs = processor(conversations=conversations, return_tensors="pt")
        inputs = {k: v.to("cuda") if hasattr(v, "to") else v for k, v in inputs.items()}
        t0 = time.time()
        with torch.no_grad():
            output_ids = model.generate(**inputs, max_new_tokens=4096)
        messages = processor.decode(output_ids)
        audio = messages[0].audio_codes_list[0]
        audio_np = audio.detach().float().cpu().numpy() if isinstance(audio, torch.Tensor) else np.asarray(audio, dtype=np.float32)
        if audio_np.ndim > 1:
            audio_np = audio_np.reshape(-1)
        out_path = os.path.join(voices_dir, f"{args.character}_audition_{i}.wav")
        sf.write(out_path, audio_np, sample_rate)
        print(f"  [{i}/{args.count}] {out_path} ({len(audio_np)/sample_rate:.1f}s in {time.time()-t0:.1f}s)")

    # Free VRAM before exiting so the next script starts clean
    del model, processor
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print(f"\nDone. Listen and pick the best one, then lock it in with:")
    print(f"  python tools/lock-voice.py {args.campaign} {args.character} --wav <chosen_audition.wav>")


if __name__ == "__main__":
    main()
