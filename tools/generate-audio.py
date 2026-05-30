#!/usr/bin/env python3
"""
Generate chapter MP3s and memoir MP3s from a session story.md file.

Dispatches to the configured TTS backend (qwen3 or moss).
Backend is read from website/assets/config.json ("ttsBackend" key, default: qwen3).

Usage:
    python tools/generate-audio.py <campaign> <session-N-story.md> [options]
    python tools/generate-audio.py waterdeep-dragon-heist campaigns/waterdeep-dragon-heist/logs/session-7-story.md
    python tools/generate-audio.py waterdeep-dragon-heist ... --scenes-only
    python tools/generate-audio.py waterdeep-dragon-heist ... --memoirs-only
    python tools/generate-audio.py waterdeep-dragon-heist ... --scene 2
    python tools/generate-audio.py waterdeep-dragon-heist ... --anchor corrin-greenbottle/anchor-brawl

Backend scripts:
    tools/backends/qwen3/generate-audio.py
    tools/backends/moss/generate-audio.py
"""

import sys
import os
import re
import json
import argparse
import unicodedata


def get_backend(campaign):
    config_path = os.path.join("website", "assets", "config.json")
    config = json.loads(open(config_path).read())
    return config["ttsBackend"]


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


MAX_SEGMENT_CHARS = 200


def split_into_chunks(text, max_chars=MAX_SEGMENT_CHARS):
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
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
                    prose_lines.append(line)
                continue
            prose_lines.append(line)
        parts = extract_segments("\n".join(prose_lines))
        if any(parts):
            scenes.append((title, parts))
    return scenes


def extract_segments(prose):
    parts, segments, current_lines = [], [], []

    def flush():
        text = clean_text(" ".join(current_lines))
        if text:
            for chunk in split_into_chunks(text):
                segments.append((None, chunk))

    for line in prose.split("\n"):
        if re.match(r"^\s*---\s*$", line):
            if current_lines:
                flush()
                current_lines = []
            if segments:
                parts.append(segments[:])
                segments.clear()
            continue
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


def parse_memoirs(campaign, session):
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


def load_voice_overrides(campaign):
    path = os.path.join("campaigns", campaign, "party", "voice-overrides.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        overrides = json.load(f)
    print(f"Voice overrides loaded: {', '.join(f'{k}→{v}' for k, v in overrides.items())}")
    return overrides


def audio_to_mp3(audio, path, sample_rate):
    import soundfile as sf
    wav_path = path.replace(".mp3", ".wav")
    sf.write(wav_path, audio, sample_rate)
    ret = os.system(f'ffmpeg -y -i "{wav_path}" -q:a 2 "{path}" 2>/dev/null')
    if ret == 0:
        os.remove(wav_path)
        return path
    print(f"  ffmpeg not found, keeping WAV: {wav_path}")
    return wav_path


def main():
    parser = argparse.ArgumentParser(description="Generate TTS audio from a story.md file")
    parser.add_argument("campaign", help="Campaign slug (e.g. waterdeep-dragon-heist)")
    parser.add_argument("story", help="Path to session-N-story.md")
    parser.add_argument("--device", default="cuda", help="Device: cuda or cpu (default: cuda)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't generate audio")
    parser.add_argument("--scene", type=int, help="Regenerate only this scene number (1-based)")
    parser.add_argument("--memoirs-only", action="store_true", help="Generate only memoir audio")
    parser.add_argument("--scenes-only", action="store_true", help="Generate only scene audio")
    parser.add_argument("--anchor", help="Memoir anchor filter: [char/]anchor-slug")
    parser.add_argument("--backend", help="Override backend: qwen3 or moss")
    parser.add_argument("--offline", action="store_true", help="Skip HuggingFace network checks, use local cache only")
    args = parser.parse_args()

    campaign = args.campaign
    story_path = args.story

    if not os.path.exists(story_path):
        print(f"Error: file not found: {story_path}")
        sys.exit(1)

    filename = os.path.basename(story_path)
    session_m = re.match(r"(session-\d+)", filename)
    if not session_m:
        print(f"Error: could not derive session from filename: {filename}")
        sys.exit(1)
    session = session_m.group(1)

    backend = args.backend or get_backend(campaign)
    print(f"Backend: {backend}")

    out_dir = os.path.join("website", campaign, "audio", session)
    os.makedirs(out_dir, exist_ok=True)

    PART_SUFFIXES = ["", "b", "c", "d", "e"]

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
        return

    voice_overrides = load_voice_overrides(campaign)

    # Load backend
    backend_dir = os.path.join(os.path.dirname(__file__), "backends", backend)
    sys.path.insert(0, backend_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location("backend_gen", os.path.join(backend_dir, "generate-audio.py"))
    be = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(be)

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        print("Offline mode — using local HuggingFace cache only.")

    voices = be.load_voices(campaign)
    model = be.load_model(voices)

    print(f"\nOutput directory: {out_dir}")

    # Parse anchor filter
    anchor_char_filter = anchor_slug_filter = None
    if args.anchor:
        if "/" in args.anchor:
            anchor_char_filter, anchor_slug_filter = args.anchor.split("/", 1)
        else:
            anchor_slug_filter = args.anchor

    # Generate scenes
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
                audio = be.generate_scene_audio(model, voices, segments, overrides=voice_overrides)
                if audio is None:
                    print("  Skipped — no audio generated.")
                    continue
                duration = len(audio) / be.SAMPLE_RATE
                print(f"  Duration: {duration:.1f}s — writing {filename}")
                print(f"  Written: {audio_to_mp3(audio, out_path, be.SAMPLE_RATE)}")

    # Generate memoirs
    if not args.scenes_only and not args.scene:
        if memoirs:
            print("\n--- Generating memoir audio ---")
        for character, anchors in memoirs.items():
            if anchor_char_filter and character != anchor_char_filter:
                continue
            print(f"\n[Memoir] {character} ({len(anchors)} anchors)")
            for anchor, segments in anchors:
                if anchor_slug_filter and anchor != anchor_slug_filter:
                    continue
                public_segs = [(t, c) for t, c in segments if t == "p"]
                private_segs = [(t, c) for t, c in segments if t == "private"]
                for suffix, segs in (("public", public_segs), ("private", private_segs)):
                    if not segs:
                        continue
                    print(f"  [{anchor}-{suffix}] ({len(segs)} blocks)")
                    audio = be.generate_memoir_audio(model, voices, character, segs, overrides=voice_overrides)
                    if audio is None:
                        print("    Skipped — no audio generated.")
                        continue
                    mp3_path = os.path.join(out_dir, f"memoir-{character}-{anchor}-{suffix}.mp3")
                    duration = len(audio) / be.SAMPLE_RATE
                    print(f"    Duration: {duration:.1f}s — {audio_to_mp3(audio, mp3_path, be.SAMPLE_RATE)}")

    import gc
    import torch
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    print("\nDone.")


if __name__ == "__main__":
    main()
