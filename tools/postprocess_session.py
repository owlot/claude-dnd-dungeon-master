#!/usr/bin/env python3
"""
Post-process a session HTML file: inject scene images at prose anchor points.

Usage:
    # List all anchor IDs in the HTML:
    python tools/postprocess_session.py <html-file> --list-anchors

    # Inject images at anchor points:
    python tools/postprocess_session.py <html-file> --anchors <json>

    # Inject and save sidecar for future HTML regenerations:
    python tools/postprocess_session.py <html-file> --anchors <json> --save-sidecar

Options:
    --list-anchors  Print all id="anchor-..." values found in the HTML, then exit.
                    Use these as keys in the --anchors JSON.

    --anchors JSON string or @filepath
              Keys are bare anchor IDs (no "anchor-" prefix) — exactly as printed
              by --list-anchors.
              Value: {"src": "images/session N/file.png", "caption": "..."}
              Images are inserted immediately BEFORE the <p id="anchor-..."> element.

              Example:
                '{"img-brawl": {"src": "images/session 1/session-01-ch2-the-brawl.png", "caption": "The Yawning Portal — the brawl breaks out"},
                  "img-deed": {"src": "images/session 1/session-01-ch7-the-deed.png", "caption": "Trollskull Manor — the deed changes hands"}}'

              Also accepts @filepath:
                --anchors @/path/to/anchors.json

    --no-backup     Skip writing a .bak backup before modifying the file.

    --save-sidecar  After injection, write the anchors mapping to a sidecar JSON file
                    alongside the HTML (session-N-images.json). story_to_html.py reads
                    that file and re-applies injection automatically on every
                    subsequent HTML regeneration.

Image injection rules:
  - Images are inserted immediately before the matching <p id="anchor-..."> element.
  - Prose anchors must be added to session-N-story.md first, then HTML regenerated,
    before running this script. Use {#anchor-slug} on its own line in the story file.
  - If an anchor already has a scene-img immediately before it, it is skipped (idempotent).
  - Multiple images are inserted in the order their anchor IDs appear in the HTML.

The file is modified in-place.
"""

import re
import json
import sys
import os
import argparse
import shutil


def load_json_arg(value):
    """Load a JSON string or @filepath into a Python object."""
    if value is None:
        return {}
    if value.startswith("@"):
        path = value[1:]
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return json.loads(value)


def list_anchors(lines):
    """Return list of bare anchor IDs (values of id="anchor-..." on p elements)."""
    anchors = []
    for line in lines:
        m = re.search(r'id="anchor-([^"]+)"', line)
        if m:
            anchors.append(m.group(1))
    return anchors


def inject_anchored_images(lines, anchors_map):
    """
    Insert images immediately before each <p id="anchor-..."> element.
    anchors_map keys are bare anchor IDs (without "anchor-" prefix).
    Values are image objects {src, caption}.
    Skips anchors that already have a scene-img immediately before them.
    Returns modified lines list.
    """
    inserted = set()
    result = []

    for i, line in enumerate(lines):
        m = re.search(r'id="anchor-([^"]+)"', line)
        if m:
            anchor_id = m.group(1)
            if anchor_id in anchors_map and anchor_id not in inserted:
                # Check if a scene-img is already present just before this anchor
                preceding = "\n".join(result[-6:]) if len(result) >= 6 else "\n".join(result)
                if 'class="scene-img"' not in preceding:
                    img = anchors_map[anchor_id]
                    src = img["src"]
                    caption = img.get("caption", "")
                    indent = "            "
                    result.append(f'{indent}<img')
                    result.append(f'{indent}    class="scene-img"')
                    result.append(f'{indent}    src="{src}"')
                    result.append(f'{indent}    alt="{anchor_id.replace("-", " ").title()}"')
                    result.append(f'{indent}/>')
                    if caption:
                        result.append(f'{indent}<p class="image-caption">{caption}</p>')
                    result.append("")
                inserted.add(anchor_id)

        result.append(line)

    missing = set(anchors_map) - inserted
    if missing:
        for anchor_id in sorted(missing):
            print(f"WARNING: no anchor found for '{anchor_id}' — image not inserted", file=sys.stderr)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Post-process a session HTML: inject scene images at prose anchor points."
    )
    parser.add_argument("html_file", help="Path to the session HTML file (modified in-place)")
    parser.add_argument(
        "--list-anchors",
        action="store_true",
        help="Print all anchor IDs in the HTML (use as --anchors keys), then exit.",
    )
    parser.add_argument(
        "--anchors",
        default=None,
        help='JSON mapping bare-anchor-id → {src, caption}, or @filepath. Keys have NO "anchor-" prefix.',
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip writing a .bak backup before modifying the file.",
    )
    parser.add_argument(
        "--save-sidecar",
        action="store_true",
        help=(
            "After injection, write the anchors mapping to session-N-images.json alongside "
            "the HTML. story_to_html.py reads this file and re-applies injection automatically "
            "on every subsequent HTML regeneration."
        ),
    )
    args = parser.parse_args()

    if not os.path.exists(args.html_file):
        print(f"Error: file not found: {args.html_file}", file=sys.stderr)
        sys.exit(1)

    with open(args.html_file, encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    if args.list_anchors:
        anchors = list_anchors(lines)
        print("Anchor IDs (use as keys in --anchors JSON, NO 'anchor-' prefix):")
        for anchor in anchors:
            print(f"  {anchor}")
        sys.exit(0)

    anchors_map = load_json_arg(args.anchors)

    if not anchors_map:
        print("Nothing to do — pass --anchors with a JSON mapping, or --list-anchors to see valid keys.", file=sys.stderr)
        sys.exit(0)

    if not args.no_backup:
        shutil.copy2(args.html_file, args.html_file + ".bak")

    lines = inject_anchored_images(lines, anchors_map)

    with open(args.html_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Postprocessed: {args.html_file}")
    print(f"  Anchors with images: {len(anchors_map)}")

    if args.save_sidecar:
        sidecar = {"anchors": anchors_map}
        sidecar_path = re.sub(r"\.html$", "-images.json", args.html_file)
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(sidecar, f, indent=2, ensure_ascii=False)
        print(f"  Sidecar written: {sidecar_path}")


if __name__ == "__main__":
    main()
