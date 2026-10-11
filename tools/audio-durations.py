#!/usr/bin/env python3
"""Write website/<campaign>/audio/durations.json: {"session-1/01-slug.mp3": seconds}.

Used by website/js/audio.js to show read times next to chapter headings.
Usage: audio-durations.py [campaign ...]   (default: every campaign under website/)
"""
import json, subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[2] / "website"
campaigns = sys.argv[1:] or [p.parent.name for p in root.glob("*/audio")]

for name in campaigns:
    audio = root / name / "audio"
    out = {}
    for mp3 in sorted(audio.glob("session-*/*.mp3")):
        if mp3.name.startswith("memoir-"):
            continue
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(mp3)],
            capture_output=True, text=True)
        try:
            out[f"{mp3.parent.name}/{mp3.name}"] = round(float(r.stdout), 1)
        except ValueError:
            print(f"skip {mp3}: {r.stderr.strip()}", file=sys.stderr)
    (audio / "durations.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{name}: {len(out)} files")
