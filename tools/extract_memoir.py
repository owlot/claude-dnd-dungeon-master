#!/usr/bin/env python3
"""
Extract memoir JSON files from a session story.md.

Usage:
    python tools/extract_memoir.py <campaign> campaigns/<campaign>/party/session-N/session-N-story.md

Output:
    campaigns/<campaign>/party/session-N/session-N-<char>.json  — one file per PC found in the story

The script discovers PC slugs dynamically from ### headings in the story — no hardcoded character list.
"""

import re
import json
import sys
import os
import argparse


def extract_memoirs(story_path, output_dir, session_number):
    with open(story_path, encoding="utf-8") as f:
        story = f.read()

    # Discover all PC slugs from ### headings that appear after {#anchor} markers
    # These are the memoir character blocks
    memoir_chars = []
    in_memoir = False
    for line in story.splitlines():
        stripped = line.strip()
        if stripped.startswith("{#"):
            in_memoir = True
            continue
        if stripped.startswith("## ") or stripped == "---":
            in_memoir = False
            continue
        if in_memoir and stripped.startswith("### "):
            slug = stripped[4:].strip()
            if slug not in memoir_chars:
                memoir_chars.append(slug)

    if not memoir_chars:
        print("No memoir character blocks found in story.", file=sys.stderr)
        sys.exit(1)

    # Split story into character sections: ### char-slug blocks
    # Build a pattern that matches any of the discovered slugs
    slug_pattern = "|".join(re.escape(s) for s in memoir_chars)
    sections = re.split(rf"### ({slug_pattern})\n", story)

    memoirs = {slug: [] for slug in memoir_chars}

    for i in range(1, len(sections), 2):
        character = sections[i]
        content = sections[i + 1] if i + 1 < len(sections) else ""

        # Line-by-line state machine — handles multi-paragraph p:/private: blocks
        current_entry = None
        current_block = None  # {"type": ..., "paragraphs": [...]}

        def flush_block(entry, block):
            if block and entry is not None and block["paragraphs"]:
                text = "\n\n".join(block["paragraphs"])
                entry["blocks"].append({"type": block["type"], "text": text})

        for line in content.splitlines():
            line = line.rstrip()

            # Scene break or scene heading — stop processing this character section entirely
            if line == "---" or line.startswith("## "):
                break

            if line.startswith("[anchor:"):
                flush_block(current_entry, current_block)
                if current_entry and current_entry["blocks"]:
                    memoirs[character].append(current_entry)
                m = re.match(r"\[anchor: ([\w-]+)\]", line)
                current_entry = {"anchor": m.group(1), "blocks": []} if m else None
                current_block = None

            elif line.startswith("p:") and current_entry is not None:
                flush_block(current_entry, current_block)
                current_block = {"type": "p", "paragraphs": [line[2:].strip()]}

            elif line.startswith("private:") and current_entry is not None:
                flush_block(current_entry, current_block)
                current_block = {"type": "private", "paragraphs": [line[8:].strip()]}

            elif line == "":
                # Blank line — flush current block and open a new empty block of same type
                if current_block is not None and current_block["paragraphs"]:
                    flush_block(current_entry, current_block)
                    current_block = {"type": current_block["type"], "paragraphs": []}

            elif line and current_block is not None and not line.startswith("[") and not line.startswith("###") and not line.startswith("{#"):
                # Continuation paragraph of the current block
                current_block["paragraphs"].append(line)

            elif line.startswith("[") or line.startswith("###") or line.startswith("{#"):
                flush_block(current_entry, current_block)
                current_block = None

        # Flush final block and entry
        flush_block(current_entry, current_block)
        if current_entry and current_entry["blocks"]:
            memoirs[character].append(current_entry)

    os.makedirs(output_dir, exist_ok=True)

    for char, entries in memoirs.items():
        out_path = os.path.join(output_dir, f"session-{session_number}-{char}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        print(f"Wrote {out_path}: {len(entries)} entries")



def main():
    parser = argparse.ArgumentParser(description="Extract memoir JSON from session story.md")
    parser.add_argument("campaign", help="Campaign slug (e.g. waterdeep-dragon-heist)")
    parser.add_argument("story", help="Path to session-N-story.md")
    parser.add_argument("--session", type=int, default=None, help="Session number (inferred from filename if omitted)")
    args = parser.parse_args()

    if not os.path.exists(args.story):
        print(f"Error: story file not found: {args.story}", file=sys.stderr)
        sys.exit(1)

    session_number = args.session
    if session_number is None:
        m = re.search(r"session-(\d+)", os.path.basename(args.story))
        if m:
            session_number = int(m.group(1))
        else:
            print("Error: could not infer session number. Use --session N.", file=sys.stderr)
            sys.exit(1)

    output_dir = os.path.join("campaigns", args.campaign, "party", f"session-{session_number}")
    extract_memoirs(args.story, output_dir, session_number)


if __name__ == "__main__":
    main()
