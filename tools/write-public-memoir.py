#!/usr/bin/env python3
"""
Write public memoir JSON files (p-blocks only) for serving without decryption.

Usage:
    python tools/write-public-memoir.py <campaign> <session-N-story.md>

For each character found in the story, reads:
    campaigns/<campaign>/party/session-N/session-N-<char>.json

Writes public-only (p blocks) JSON to:
    website/<campaign>/assets/memoirs/session-N-<char>-public.json

Anchors with no p blocks are omitted entirely.
"""

import re
import json
import sys
import os
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign")
    parser.add_argument("story", help="Path to session-N-story.md")
    parser.add_argument("--session", type=int, default=None)
    args = parser.parse_args()

    session_number = args.session
    if session_number is None:
        m = re.search(r"session-(\d+)", os.path.basename(args.story))
        if m:
            session_number = int(m.group(1))
        else:
            print("Error: could not infer session number. Use --session N.", file=sys.stderr)
            sys.exit(1)

    memoir_dir = os.path.join("campaigns", args.campaign, "party", f"session-{session_number}")
    output_dir = os.path.join("website", args.campaign, "assets", "memoirs")
    os.makedirs(output_dir, exist_ok=True)

    prefix = f"session-{session_number}-"
    found = False

    for filename in sorted(os.listdir(memoir_dir)):
        if not filename.startswith(prefix) or not filename.endswith(".json"):
            continue
        char = filename[len(prefix):-5]

        with open(os.path.join(memoir_dir, filename), encoding="utf-8") as f:
            entries = json.load(f)

        public_entries = []
        for entry in entries:
            public_blocks = [b for b in entry.get("blocks", []) if b.get("type") == "p"]
            if public_blocks:
                public_entries.append({"anchor": entry["anchor"], "blocks": public_blocks})

        out_path = os.path.join(output_dir, f"session-{session_number}-{char}-public.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(public_entries, f, indent=2, ensure_ascii=False)
        print(f"Wrote {out_path}: {len(public_entries)} entries with public blocks")
        found = True

    if not found:
        print(f"No memoir JSON files found in {memoir_dir} for session {session_number}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
