#!/usr/bin/env python3
"""
Generate chapter MP3s and memoir MP3s from a session story.md file using MOSS-TTS v1.5.

Usage:
    python tools/generate-audio.py <campaign-slug> <session-N-story.md>
    python tools/generate-audio.py waterdeep-dragon-heist campaigns/waterdeep-dragon-heist/party/session-7/session-7-story.md
    python tools/generate-audio.py waterdeep-dragon-heist campaigns/waterdeep-dragon-heist/party/session-7/session-7-story.md --scene 2
    python tools/generate-audio.py waterdeep-dragon-heist campaigns/waterdeep-dragon-heist/party/session-7/session-7-story.md --memoirs-only

Voices are loaded from:
    website/<campaign>/audio/voices/<speaker-slug>.wav   (campaign characters)
    website/audio/voices/narrator.wav                    (global narrator)

Each voice WAV is paired with its introduction transcript from:
    campaigns/<campaign>/info/introductions/<speaker-slug>.md

Speaker slugs in the story must match introduction file slugs (e.g. [caelith-morn], [yagra-stonefist]).
Run tools/audition-voice-ref.py and tools/lock-voice.py first.

Output (scenes):
    website/<campaign>/audio/<session>/01-<scene-slug>.mp3
    ...

Output (memoirs):
    website/<campaign>/audio/<session>/memoir-<character-slug>-<anchor>.mp3
"""

import re
import sys
import os
import json
import argparse
import unicodedata
import numpy as np
import soundfile as sf
import torch

SAMPLE_RATE = 24000
MAX_SEGMENT_CHARS = 200

# Silence trimming — applied to every model-generated audio chunk.
# MOSS-TTS occasionally produces multi-second silence bursts mid-output.
SILENCE_MAX_S = 0.25      # cap any silence run to this length (seconds)
SILENCE_THRESHOLD = 0.001  # samples below this amplitude are considered silent

# Phonetic substitutions — applied before TTS to ensure consistent pronunciation.
# Keys are regex patterns (case-insensitive), values are phonetic replacements.
PHONETIC_SUBSTITUTIONS = {
    r"\bLylnyler\b": "lil-nigh-ler",
    r"\bFienderck\b": "feen-derk",
    r"\bCaelith\b": "caylith",
    r"\bLif\b": "liv",
    r"\bRenaer\b": "rehnar",
}

# How many segments to generate in one model.generate() call.
# Batching > 1 risks OOM on long segments — keep at 1 until VRAM headroom is confirmed.
BATCH_SIZE = 1

# MOSS-TTS v1.5 generation kwargs
GEN_KWARGS = dict(
    max_new_tokens=1500,   # ~100s of audio — well above any single segment
    text_temperature=0.1,
    audio_temperature=0.6,
    audio_top_p=0.8,
    audio_top_k=25,
    audio_repetition_penalty=1.3,
)


# ---------------------------------------------------------------------------
# Voice loading
# ---------------------------------------------------------------------------

def load_introduction_text(campaign, slug):
    """Load the body text from an introduction file — used as the voice transcript."""
    intro_path = os.path.join("campaigns", campaign, "info", "introductions", f"{slug}.md")
    if not os.path.exists(intro_path):
        return None
    with open(intro_path, encoding="utf-8") as f:
        content = f.read()
    fm_match = re.match(r"^---\n.*?\n---\n(.*)", content, re.DOTALL)
    if fm_match:
        return fm_match.group(1).strip()
    return content.strip()


REF_MAX_SECONDS = 8  # trim reference WAVs to this length to save VRAM during inference


def trim_wav(src_path, dst_path, max_seconds):
    """Trim a WAV to max_seconds and save to dst_path. Returns dst_path."""
    import torchaudio
    wav, sr = torchaudio.load(src_path)
    max_samples = int(sr * max_seconds)
    if wav.shape[-1] > max_samples:
        wav = wav[:, :max_samples]
        torchaudio.save(dst_path, wav, sr)
        return dst_path
    return src_path  # already short enough, use original


def load_voices(campaign):
    """Load locked voice WAVs (trimmed for VRAM efficiency) and their introduction transcripts.

    Returns: {slug: {"wav": path, "transcript": text}}

    Campaign-specific voices: website/<campaign>/audio/voices/<slug>.wav
    Global voices (narrator):  website/audio/voices/narrator.wav
    Campaign voices take priority over global if the same slug exists in both.

    Reference WAVs longer than REF_MAX_SECONDS are trimmed to a temp file.
    """
    import tempfile
    voices = {}
    _tmp_dir = tempfile.mkdtemp(prefix="dm_voices_")

    # Load global voices first (narrator)
    global_dir = os.path.join("website", "audio", "introductions")
    if os.path.exists(global_dir):
        for filename in os.listdir(global_dir):
            if filename.endswith(".wav") and not any(x in filename for x in ["_audition_", "_ref"]):
                slug = filename[:-4]
                src = os.path.join(global_dir, filename)
                wav_path = trim_wav(src, os.path.join(_tmp_dir, filename), REF_MAX_SECONDS)
                voices[slug] = {"wav": wav_path, "transcript": None}

    # Load campaign-specific voices (override global if same slug)
    campaign_dir = os.path.join("website", campaign, "audio", "introductions")
    if os.path.exists(campaign_dir):
        for filename in os.listdir(campaign_dir):
            if filename.endswith(".wav") and not any(x in filename for x in ["_audition_", "_ref"]):
                slug = filename[:-4]
                src = os.path.join(campaign_dir, filename)
                wav_path = trim_wav(src, os.path.join(_tmp_dir, filename), REF_MAX_SECONDS)
                transcript = load_introduction_text(campaign, slug)
                voices[slug] = {"wav": wav_path, "transcript": transcript}

    if voices:
        print(f"Loaded voices: {', '.join(sorted(voices))}")
    else:
        print("Warning: no locked voices found.")
        print("Run tools/audition-voice-ref.py and tools/lock-voice.py first.")

    return voices


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def slugify(text):
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def clean_text(text):
    text = re.sub(r"\{#[^}]+\}", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
    text = re.sub(r"\[anchor:[^\]]+\]", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_into_chunks(text, max_chars=MAX_SEGMENT_CHARS):
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for sentence in sentences:
        if not sentence.strip():
            continue
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = (current + " " + sentence).strip() if current else sentence
    if current:
        chunks.append(current.strip())
    return chunks if chunks else [text]


# ---------------------------------------------------------------------------
# Parsing — scenes
# ---------------------------------------------------------------------------

def parse_story(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r"^#[^#].*?\n---\n", "", content, flags=re.DOTALL)
    scene_blocks = re.split(r"\n## ", content)

    scenes = []
    for block in scene_blocks:
        if not block.strip():
            continue
        lines = block.split("\n")
        title = lines[0].strip()
        prose_lines = []
        in_memoir = False
        for line in lines[1:]:
            if re.match(r"^### ", line):
                in_memoir = True
                continue
            if in_memoir:
                if re.match(r"^---\s*$", line):
                    in_memoir = False
                    # Emit the --- so extract_segments can split the scene here
                    prose_lines.append(line)
                continue
            prose_lines.append(line)
        parts = extract_segments("\n".join(prose_lines))
        if any(parts):
            scenes.append((title, parts))

    return scenes


def merge_narrator_segments(segments, max_chars=MAX_SEGMENT_CHARS):
    """Merge consecutive narrator (None) segments into longer chunks."""
    merged = []
    buf = None
    for speaker, text in segments:
        if speaker is None:
            if buf is None:
                buf = text
            elif len(buf) + 1 + len(text) <= max_chars:
                buf = buf + " " + text
            else:
                merged.append((None, buf))
                buf = text
        else:
            if buf is not None:
                merged.append((None, buf))
                buf = None
            merged.append((speaker, text))
    if buf is not None:
        merged.append((None, buf))
    return merged


def extract_segments(prose):
    """Parse prose into parts split at scene-break markers (---).

    Returns a list of segment-lists: one list per part.
    Most scenes have one part; scenes with a mid-scene --- have two or more.
    Each segment-list is a list of (speaker_slug_or_None, text) tuples.
    """
    parts = []
    segments = []
    current_lines = []

    def flush():
        text = clean_text(" ".join(current_lines))
        if text:
            for chunk in split_into_chunks(text):
                segments.append((None, chunk))

    for line in prose.split("\n"):
        # Scene-break marker — flush current part and start a new one
        if re.match(r"^\s*---\s*$", line):
            if current_lines:
                flush()
                current_lines = []
            if segments:
                parts.append(segments)
                segments = []
            continue

        # Legacy decorative breaks (--- handled above; skip *** etc.)
        if re.match(r"^\s*[*·]{3,}\s*$", line):
            if current_lines:
                flush()
                current_lines = []
            continue

        speaker_match = re.match(r"^\[([^\]]+)\]:\s*(.*)", line)
        if speaker_match:
            if current_lines:
                flush()
                current_lines = []
            speaker = speaker_match.group(1).lower()
            text = speaker_match.group(2).strip()
            text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
            text = text.strip('""''"\'').strip()
            # Skip punctuation-only segments (e.g. "—") — produce silence
            if text and re.search(r'\w', text):
                for chunk in split_into_chunks(text, max_chars=300):
                    segments.append((speaker, chunk))
            continue

        if not line.strip():
            if current_lines:
                flush()
                current_lines = []
            continue

        if re.match(r"^\*\*(Campaign|Date|In-game):", line):
            continue

        current_lines.append(line.strip())

    if current_lines:
        flush()
    if segments:
        parts.append(segments)

    return parts if parts else [[]]


# ---------------------------------------------------------------------------
# Parsing — memoirs
# ---------------------------------------------------------------------------

def parse_memoirs(campaign, session):
    """Returns: {character_slug: [(anchor, [(type, text), ...]), ...]}"""
    memoirs = {}
    memoir_dir = os.path.join("campaigns", campaign, "party", session)

    if not os.path.exists(memoir_dir):
        return memoirs

    for filename in os.listdir(memoir_dir):
        if not filename.startswith(session + "-") or not filename.endswith(".json"):
            continue
        character_slug = filename[len(session) + 1:-5]

        with open(os.path.join(memoir_dir, filename), encoding="utf-8") as f:
            entries = json.load(f)

        anchors = []
        for entry in entries:
            anchor = entry.get("anchor", "")
            segments = []
            for block in entry.get("blocks", []):
                text = clean_text(block.get("text", ""))
                if text:
                    for chunk in split_into_chunks(text):
                        segments.append((block.get("type", "p"), chunk))
            if segments:
                anchors.append((anchor, segments))

        if anchors:
            memoirs[character_slug] = anchors

    return memoirs


# ---------------------------------------------------------------------------
# Audio generation
# ---------------------------------------------------------------------------

def load_models(device):
    from transformers import AutoModel, AutoProcessor

    torch.backends.cuda.enable_cudnn_sdp(False)
    torch.backends.cuda.enable_flash_sdp(True)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)

    import gc
    gc.collect()

    # Reset the CUDA context entirely to clear any stale allocator state
    # from previous processes before loading the model.
    if torch.cuda.is_available():
        torch.cuda.init()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()

    # Disable transformers' caching_allocator_warmup — it pre-allocates the full
    # model size as a warmup buffer which OOMs on 24GB with the 8B model loaded.
    import transformers.modeling_utils as _mu
    _mu.caching_allocator_warmup = lambda *a, **kw: None

    print(f"Loading MOSS-TTS v1.5 on {device}...")
    processor = AutoProcessor.from_pretrained("OpenMOSS-Team/MOSS-TTS-v1.5", trust_remote_code=True)
    processor.audio_tokenizer = processor.audio_tokenizer.to(device)
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    model = AutoModel.from_pretrained(
        "OpenMOSS-Team/MOSS-TTS-v1.5",
        trust_remote_code=True,
        dtype=dtype,
        device_map="auto" if device == "cuda" else None,
    )
    if device != "cuda":
        model = model.to(device)
    model.eval()
    print("Model loaded.")
    return model, processor


def load_voice_overrides(campaign):
    """Load campaigns/<campaign>/party/voice-overrides.json if it exists.

    Returns {speaker_slug: voice_slug} — maps a slug that has no dedicated WAV
    to the generic voice slug that should be used instead.

    Example file:
        {
          "male-mid-minor":      "male-mid",
          "male-young-minor":    "male-young",
          "dock-ward-half-orc":  "male-mid",
          "unknown-man":         "male-weathered"
        }
    """
    path = os.path.join("campaigns", campaign, "party", "voice-overrides.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        overrides = json.load(f)
    print(f"Voice overrides loaded: {', '.join(f'{k}→{v}' for k, v in overrides.items())}")
    return overrides


def resolve_voice(voices, speaker_slug, overrides=None):
    """Return the voice dict for a speaker slug, falling back to narrator.

    If speaker_slug has no direct WAV, check overrides before falling back.
    overrides: {speaker_slug: voice_slug} from load_voice_overrides().
    """
    if speaker_slug and speaker_slug in voices:
        return voices[speaker_slug]
    if overrides and speaker_slug in overrides:
        mapped = overrides[speaker_slug]
        if mapped in voices:
            return voices[mapped]
    if speaker_slug:
        for key in voices:
            if key.startswith(speaker_slug + "-"):
                return voices[key]
    return voices.get("narrator")


def apply_substitutions(text):
    for pattern, replacement in PHONETIC_SUBSTITUTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.replace("—", ",")


def generate_batch(model, processor, voices, items, device, overrides=None):
    """Generate audio for a list of (speaker_slug, text) pairs in one model call.

    Returns a list of numpy arrays (or None per item on failure), same order as input.
    Items with the same voice are batched together; different voices are grouped separately.
    """
    if not items:
        return []

    results = [None] * len(items)

    # Group by resolved voice path so all items in a batch share the same reference wav.
    # Items with different voices must be separate calls.
    from itertools import groupby
    groups = []
    for i, (speaker_slug, text) in enumerate(items):
        voice = resolve_voice(voices, speaker_slug, overrides)
        wav_path = voice["wav"] if voice else None
        groups.append((i, wav_path, voice, apply_substitutions(text)))

    # Sort by wav_path so we can group consecutive same-voice items
    def by_wav(x): return x[1] or ""
    sorted_groups = sorted(range(len(groups)), key=lambda i: groups[i][1] or "")

    i = 0
    while i < len(sorted_groups):
        # Collect a batch of up to BATCH_SIZE items with the same voice
        base_idx = sorted_groups[i]
        wav_path = groups[base_idx][1]
        batch_indices = [base_idx]
        j = i + 1
        while j < len(sorted_groups) and len(batch_indices) < BATCH_SIZE:
            idx = sorted_groups[j]
            if groups[idx][1] == wav_path:
                batch_indices.append(idx)
                j += 1
            else:
                break
        i = j if j > i + 1 else i + len(batch_indices)

        voice = groups[batch_indices[0]][2]
        texts = [groups[idx][3] for idx in batch_indices]

        try:
            conversations = []
            for text in texts:
                if voice:
                    conversations.append([processor.build_user_message(text=text, reference=[voice["wav"]], language="English")])
                else:
                    conversations.append([processor.build_user_message(text=text, language="English")])

            inputs = processor(conversations=conversations, mode="generation", return_tensors="pt")
            inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

            with torch.no_grad():
                output_ids = model.generate(**inputs, **GEN_KWARGS)

            messages = processor.decode(output_ids)

            for k, (orig_idx, msg) in enumerate(zip(batch_indices, messages)):
                if not msg.audio_codes_list:
                    speaker_slug = items[orig_idx][0]
                    print(f"  Warning: model returned empty audio_codes_list [{speaker_slug or 'narrator'}]")
                    continue
                audio = msg.audio_codes_list[0]
                audio_np = audio.detach().float().cpu().numpy() if isinstance(audio, torch.Tensor) else np.asarray(audio, dtype=np.float32)
                if audio_np.ndim > 1:
                    audio_np = audio_np.reshape(-1)
                results[orig_idx] = audio_np

            del inputs, output_ids, messages
            torch.cuda.empty_cache()

        except Exception as e:
            for orig_idx in batch_indices:
                speaker_slug = items[orig_idx][0]
                print(f"  Warning: failed [{speaker_slug or 'narrator'}]: {e}")

    return results


def generate_segment(model, processor, voices, speaker_slug, text, device, overrides=None):
    """Generate a single segment. Thin wrapper around generate_batch for backwards compat."""
    results = generate_batch(model, processor, voices, [(speaker_slug, text)], device, overrides=overrides)
    return results[0] if results else None


def strip_internal_silence(audio, sr=SAMPLE_RATE, max_silence_s=SILENCE_MAX_S, threshold=SILENCE_THRESHOLD):
    """Cap any continuous silent region in audio to max_silence_s seconds.

    MOSS-TTS occasionally generates multi-second silence bursts mid-output.
    Excess silence is replaced with zeros rather than removed — removing samples
    creates phase discontinuities that sound like glitches.
    """
    max_samples = int(sr * max_silence_s)
    result = audio.copy()
    silent = np.abs(audio) < threshold

    i = 0
    while i < len(audio):
        if silent[i]:
            j = i
            while j < len(audio) and silent[j]:
                j += 1
            run_len = j - i
            if run_len > max_samples:
                # Zero out the tail of this silence run instead of splicing it out
                result[i + max_samples:j] = 0.0
            i = j
        else:
            i += 1

    return result


def assemble_audio(chunks):
    silence_lead   = np.zeros(int(SAMPLE_RATE * 1.0))  # leading pause so players don't clip the start
    silence_short  = np.zeros(int(SAMPLE_RATE * 0.3))
    silence_long   = np.zeros(int(SAMPLE_RATE * 0.6))
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


def generate_scene_audio(model, processor, voices, segments, device, overrides=None):
    for speaker, text in segments:
        label = speaker or "narrator"
        print(f"    [{label}]: {text[:60]}{'...' if len(text) > 60 else ''}")
    audio_list = generate_batch(model, processor, voices, segments, device, overrides=overrides)
    chunks = [(speaker is not None, audio) for (speaker, _), audio in zip(segments, audio_list)]
    return assemble_audio(chunks)


def generate_memoir_audio(model, processor, voices, character_slug, segments, device, overrides=None):
    """Generate audio for one anchor's memoir blocks. Returns numpy array or None."""
    silence_lead  = np.zeros(int(SAMPLE_RATE * 1.0))  # leading pause, same as scene audio
    silence_inter = np.zeros(int(SAMPLE_RATE * 0.4))

    for block_type, text in segments:
        print(f"      [{block_type}]: {text[:60]}{'...' if len(text) > 60 else ''}")

    items = [(character_slug, text) for _, text in segments]
    audio_list = generate_batch(model, processor, voices, items, device, overrides=overrides)

    all_chunks = [silence_lead]
    for audio in audio_list:
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio from a story.md file")
    parser.add_argument("campaign", help="Campaign slug (e.g. waterdeep-dragon-heist)")
    parser.add_argument("story", help="Path to session-N-story.md")
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu (default: cuda)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't generate audio")
    parser.add_argument("--scene", type=int, help="Regenerate only this scene number (1-based)")
    parser.add_argument("--memoirs-only", action="store_true", help="Generate only memoir audio")
    parser.add_argument("--scenes-only", action="store_true", help="Generate only scene audio")
    parser.add_argument("--anchor", help="Regenerate only this memoir anchor (e.g. anchor-brawl), optionally prefixed with character slug: corrin/anchor-brawl")
    args = parser.parse_args()

    story_path = args.story
    campaign = args.campaign

    if not os.path.exists(story_path):
        print(f"Error: file not found: {story_path}")
        sys.exit(1)

    filename = os.path.basename(story_path)
    session_m = re.match(r"(session-\d+)", filename)
    if not session_m:
        print(f"Error: could not derive session from filename: {filename}")
        sys.exit(1)
    session = session_m.group(1)

    out_dir = os.path.join("website", campaign, "audio", session)
    os.makedirs(out_dir, exist_ok=True)

    # Load voices and overrides
    voices = load_voices(campaign)
    voice_overrides = load_voice_overrides(campaign)

    # Parse
    PART_SUFFIXES = ["", "b", "c", "d", "e"]  # up to 5 parts per scene

    scenes = parse_story(story_path)
    print(f"Found {len(scenes)} scenes:")
    for i, (title, parts) in enumerate(scenes, 1):
        total_segs = sum(len(p) for p in parts)
        parts_label = f", {len(parts)} parts" if len(parts) > 1 else ""
        print(f"  {i:02d}. {title} ({total_segs} segments{parts_label})")

    memoirs = parse_memoirs(campaign, session)
    if memoirs:
        print(f"Found memoirs for: {', '.join(memoirs)}")
    else:
        print("No memoir files found.")

    if args.dry_run:
        print("\nDry run — no audio generated.")
        for i, (title, parts) in enumerate(scenes, 1):
            slug = slugify(title)
            for j, segments in enumerate(parts):
                suffix = PART_SUFFIXES[j] if j < len(PART_SUFFIXES) else str(j)
                print(f"\n## {title}{f' (part {suffix})' if suffix else ''}")
                for speaker, text in segments:
                    label = f"[{speaker}]" if speaker else "[narrator]"
                    print(f"  {label} ({len(text)}c): {text[:80]}{'...' if len(text) > 80 else ''}")
        for char, anchors in memoirs.items():
            print(f"\n### Memoir: {char}")
            for anchor, segments in anchors:
                print(f"  [{anchor}]")
                for btype, text in segments:
                    print(f"    [{btype}] ({len(text)}c): {text[:80]}{'...' if len(text) > 80 else ''}")
        return

    print(f"\nOutput directory: {out_dir}")
    model, processor = load_models(args.device)

    # Generate scenes — each part of a split scene gets its own file (02-slug.mp3, 02b-slug.mp3, ...)
    if not args.memoirs_only:
        for i, (title, parts) in enumerate(scenes, 1):
            if args.scene and i != args.scene:
                continue
            slug = slugify(title)
            for j, segments in enumerate(parts):
                suffix = PART_SUFFIXES[j] if j < len(PART_SUFFIXES) else str(j)
                filename = f"{i:02d}{suffix}-{slug}.mp3"
                out_path = os.path.join(out_dir, filename)
                label = f"part {suffix}" if suffix else "single"
                print(f"\n[Scene {i}/{len(scenes)}] {title} ({label}, {len(segments)} segments)")
                audio = generate_scene_audio(model, processor, voices, segments, args.device, overrides=voice_overrides)
                if audio is None:
                    print("  Skipped — no audio generated.")
                    continue
                duration = len(audio) / SAMPLE_RATE
                print(f"  Duration: {duration:.1f}s — writing {filename}")
                print(f"  Written: {audio_to_mp3(audio, out_path)}")

    # Generate memoirs — one file per anchor per character
    if not args.scenes_only:
        # Parse optional --anchor filter: "corrin/anchor-brawl" or just "anchor-brawl"
        anchor_char_filter = None
        anchor_slug_filter = None
        if args.anchor:
            if "/" in args.anchor:
                anchor_char_filter, anchor_slug_filter = args.anchor.split("/", 1)
            else:
                anchor_slug_filter = args.anchor

        if memoirs:
            print("\n--- Generating memoir audio ---")
        for character, anchors in memoirs.items():
            if anchor_char_filter and character != anchor_char_filter:
                continue
            print(f"\n[Memoir] {character} ({len(anchors)} anchors)")
            for anchor, segments in anchors:
                if anchor_slug_filter and anchor != anchor_slug_filter:
                    continue
                print(f"  [{anchor}] ({len(segments)} blocks)")
                audio = generate_memoir_audio(model, processor, voices, character, segments, args.device, overrides=voice_overrides)
                if audio is None:
                    print("    Skipped — no audio generated.")
                    continue
                mp3_path = os.path.join(out_dir, f"memoir-{character}-{anchor}.mp3")
                duration = len(audio) / SAMPLE_RATE
                print(f"    Duration: {duration:.1f}s — {audio_to_mp3(audio, mp3_path)}")

    del model, processor
    import gc
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    print("\nDone.")


if __name__ == "__main__":
    main()
