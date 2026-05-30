#!/usr/bin/env python3
"""
Compare Qwen3 vs MOSS-TTS voice cloning output for the same text and reference.

Usage:
    python tools/compare-backends.py <campaign> <character-slug> [--text "custom text"]

Outputs:
    /tmp/compare-<character>-qwen3.wav
    /tmp/compare-<character>-moss.wav

Example:
    python tools/compare-backends.py waterdeep-dragon-heist yagra-stonefist
"""

import sys
import os
import argparse
import numpy as np
import soundfile as sf
import torch

DEFAULT_TEXT = (
    "I don't do this for glory or gratitude. "
    "You pay me, I do the job, and I do it right — that's the only contract that means anything to me. "
    "Don't mistake competence for loyalty. They're not the same thing."
)

SAMPLE_RATE = 24000


def run_qwen3(character, campaign, text, wav_path, pt_path, out_path, xvector=False):
    print("\n── Qwen3 ──────────────────────────────────────")

    from qwen_tts import Qwen3TTSModel

    print("Loading Qwen3 Base model...")
    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-Base", device_map="cuda", dtype=torch.float16
    )

    if xvector:
        print(f"Mode: x_vector_only (from WAV: {wav_path})")
        if not os.path.exists(wav_path):
            print(f"Error: .wav file not found: {wav_path}")
            return
        audio, sr_ref = sf.read(wav_path)
        prompt = model.create_voice_clone_prompt(ref_audio=(audio, sr_ref), x_vector_only_mode=True)
        out_path = out_path.replace("-qwen3.wav", "-qwen3-xvec.wav")
    else:
        print(f"Mode: ICL clone (from .pt: {pt_path})")
        if not os.path.exists(pt_path):
            print(f"Error: .pt file not found: {pt_path}")
            return
        prompt = torch.load(pt_path, weights_only=False)

    print(f"Generating: {text[:60]}...")
    wavs, sr = model.generate_voice_clone(
        text=text,
        language="English",
        voice_clone_prompt=prompt,
        max_new_tokens=800,
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
    sf.write(out_path, wavs[0], sr)
    print(f"Written: {out_path} ({len(wavs[0])/sr:.1f}s)")

    del model, prompt
    import gc
    gc.collect()
    torch.cuda.empty_cache()


def run_moss(character, campaign, text, wav_path, pt_path, out_path):
    print("\n── MOSS-TTS ────────────────────────────────────")
    if not os.path.exists(wav_path):
        print(f"Error: .wav file not found: {wav_path}")
        print("Run: python tools/lock-voice.py <campaign> <character> --backend moss")
        return

    import gc
    import transformers.modeling_utils as _mu
    _mu.caching_allocator_warmup = lambda *a, **kw: None

    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)

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

    print(f"Generating: {text[:60]}...")
    conversations = [[processor.build_user_message(text=text, reference=[wav_path], language="English")]]
    inputs = processor(conversations=conversations, mode="generation", return_tensors="pt")
    inputs = {k: v.to("cuda") if hasattr(v, "to") else v for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=1500,
            text_temperature=0.1,
            audio_temperature=0.6,
            audio_top_p=0.8,
            audio_top_k=25,
            audio_repetition_penalty=1.3,
        )

    messages = processor.decode(output_ids)
    audio = messages[0].audio_codes_list[0]
    audio_np = audio.detach().float().cpu().numpy() if isinstance(audio, torch.Tensor) else np.asarray(audio, dtype=np.float32)
    if audio_np.ndim > 1:
        audio_np = audio_np.reshape(-1)

    sf.write(out_path, audio_np, SAMPLE_RATE)
    print(f"Written: {out_path} ({len(audio_np)/SAMPLE_RATE:.1f}s)")

    del model, processor, inputs, output_ids, messages
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", help="Campaign slug")
    parser.add_argument("character", help="Character slug")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Text to synthesize")
    parser.add_argument("--backend", choices=["qwen3", "moss", "both"], default="both",
                        help="Which backend(s) to run (default: both)")
    parser.add_argument("--xvector", action="store_true",
                        help="Qwen3: use x_vector_only_mode (speaker embedding only, no ICL)")
    args = parser.parse_args()

    voices_dir = os.path.join("website", args.campaign, "audio", "voices")
    wav_path = os.path.join(voices_dir, f"{args.character}.wav")
    pt_path  = os.path.join(voices_dir, f"{args.character}.pt")

    print(f"Character: {args.character}")
    print(f"WAV:       {wav_path} {'✓' if os.path.exists(wav_path) else '✗ missing'}")
    print(f"PT:        {pt_path}  {'✓' if os.path.exists(pt_path) else '✗ missing'}")
    print(f"Text:      {args.text[:80]}...")

    qwen3_out = f"/tmp/compare-{args.character}-qwen3.wav"
    moss_out  = f"/tmp/compare-{args.character}-moss.wav"

    if args.backend in ("qwen3", "both"):
        run_qwen3(args.character, args.campaign, args.text, wav_path, pt_path, qwen3_out,
                  xvector=args.xvector)

    if args.backend in ("moss", "both"):
        run_moss(args.character, args.campaign, args.text, wav_path, pt_path, moss_out)

    print("\n── Results ─────────────────────────────────────")
    if args.backend in ("qwen3", "both"):
        print(f"Qwen3: {qwen3_out}")
    if args.backend in ("moss", "both"):
        print(f"MOSS:  {moss_out}")


if __name__ == "__main__":
    main()
