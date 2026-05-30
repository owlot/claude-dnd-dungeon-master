#!/usr/bin/env python3
"""
Generate narrator audition samples using MOSS-TTS VoiceDesign.
Called by tools/audition-narrator.py — do not run directly.
"""

import os
import gc
import time
import numpy as np
import soundfile as sf
import torch

TEXT = (
    "The city of Waterdeep never truly sleeps. Even in the hours before dawn, "
    "when the last taverns have shuttered and the watch patrols echo alone through "
    "the cobbled streets, something is always moving in the dark. "
    "Tonight, three people sat around a table in a manor that smelled of sawdust and old timber, "
    "and made the kind of plans that tend to change everything."
)
INSTRUCT = (
    "A deep British male narrator with gravitas and warmth. "
    "Slightly faster than average pace, authoritative and confident — the voice of a master storyteller "
    "reading a dark fantasy novel aloud. Rich baritone, clear diction, brisk but never rushed."
)

GEN_KWARGS = dict(
    max_new_tokens=4096,
    audio_temperature=1.5,
    audio_top_p=0.6,
    audio_top_k=50,
    audio_repetition_penalty=1.1,
)

SAMPLE_RATE = 24000


def run(count, voices_dir):
    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)

    import transformers.modeling_utils as _mu
    _mu.caching_allocator_warmup = lambda *a, **kw: None

    from transformers import AutoModel, AutoProcessor
    print("Loading MOSS-VoiceGenerator...")
    processor = AutoProcessor.from_pretrained(
        "OpenMOSS-Team/MOSS-VoiceGenerator", trust_remote_code=True, normalize_inputs=True
    )
    model = AutoModel.from_pretrained(
        "OpenMOSS-Team/MOSS-VoiceGenerator",
        trust_remote_code=True,
        dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()

    print(f"Generating {count} narrator audition samples...\n")
    for i in range(1, count + 1):
        conversations = [[processor.build_user_message(text=TEXT, instruction=INSTRUCT)]]
        batch = processor(conversations=conversations, mode="generation")
        input_ids = batch["input_ids"].to("cuda")
        attention_mask = batch["attention_mask"].to("cuda")

        t0 = time.time()
        with torch.no_grad():
            output_ids = model.generate(input_ids=input_ids, attention_mask=attention_mask, **GEN_KWARGS)

        messages = processor.decode(output_ids)
        audio = messages[0].audio_codes_list[0]
        audio_np = audio.detach().float().cpu().numpy() if isinstance(audio, torch.Tensor) else np.asarray(audio, dtype=np.float32)
        if audio_np.ndim > 1:
            audio_np = audio_np.reshape(-1)

        out_path = os.path.join(voices_dir, f"narrator_audition_{i}.wav")
        sf.write(out_path, audio_np, SAMPLE_RATE)
        print(f"  [{i}/{count}] {out_path} ({len(audio_np)/SAMPLE_RATE:.1f}s in {time.time()-t0:.1f}s)")

        del batch, input_ids, attention_mask, output_ids, messages
        torch.cuda.empty_cache()

    del model, processor
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
