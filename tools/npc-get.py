#!/usr/bin/env python3
"""Extract a single named section from a unified NPC file."""

import sys
import re
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print("Usage: python tools/npc-get.py <campaign> <slug> <section>", file=sys.stderr)
        print("       python tools/npc-get.py <campaign> <slug> --list", file=sys.stderr)
        sys.exit(1)

    campaign = sys.argv[1]
    slug = sys.argv[2]
    section_arg = sys.argv[3] if len(sys.argv) > 3 else None

    npc_path = Path(f"campaigns/{campaign}/info/npcs/{slug}.md")

    if not npc_path.exists():
        print(f"NPC not found: {slug}", file=sys.stderr)
        sys.exit(1)

    content = npc_path.read_text(encoding="utf-8")

    # Find all ## sections
    section_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(section_pattern.finditer(content))

    if section_arg == "--list":
        for m in matches:
            print(m.group(1).strip())
        return

    if not section_arg:
        print("Usage: python tools/npc-get.py <campaign> <slug> <section>", file=sys.stderr)
        sys.exit(1)

    # Find the requested section (case-insensitive)
    target = section_arg.lower()
    found_match = None
    for m in matches:
        if m.group(1).strip().lower() == target:
            found_match = m
            break

    if found_match is None:
        print(f"Section '{section_arg}' not found in {slug}", file=sys.stderr)
        sys.exit(1)

    # Extract content from end of header line to next ## or end of file
    start = found_match.end()
    # Find next ## header
    next_match = None
    for m in matches:
        if m.start() > found_match.start():
            next_match = m
            break

    if next_match:
        section_content = content[start:next_match.start()]
    else:
        section_content = content[start:]

    print(section_content.strip())


if __name__ == "__main__":
    main()
