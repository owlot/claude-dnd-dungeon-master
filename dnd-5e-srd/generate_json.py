#!/usr/bin/env python3
"""
Regenerate dnd-5e-srd/json/*.json from dnd-5e-srd/markdown/*.md.

Replaces the broken TypeScript generator. Produces the same nested JSON
structure (headings as keys, content as lists) without the apostrophe bug.

Usage:
  python3 dnd-5e-srd/generate_json.py              # regenerate all files
  python3 dnd-5e-srd/generate_json.py 02 classes   # regenerate one file
"""

import sys
import json
import re
from pathlib import Path

BASE     = Path(__file__).parent
MD_DIR   = BASE / "markdown"
JSON_DIR = BASE / "json"


def parse_markdown(text: str) -> dict:
    """
    Parse a markdown file into a nested dict matching the original TS output:
      { "Section": { "content": [...], "Subsection": { "content": [...] } } }

    Supports both ATX headings (# H1, ## H2) and setext headings (text\n=== or text\n---).
    Content items are strings, bullet lists (nested Python lists), or {"table": {...}} dicts.
    """

    # Normalise setext headings to ATX first
    setext_re = re.compile(r'^(.+)\n([=\-]{2,})\s*$', re.MULTILINE)
    def replace_setext(m):
        title = m.group(1).strip()
        level = 1 if m.group(2)[0] == '=' else 2
        return '#' * level + ' ' + title
    text = setext_re.sub(replace_setext, text)

    root: dict = {}
    stack: list = []  # [(level, node_dict)]

    def current_node() -> dict:
        return stack[-1][1] if stack else root

    def ensure_content(node: dict) -> list:
        if "content" not in node:
            node["content"] = []
        return node["content"]

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # --- ATX Heading ---
        m = re.match(r'^(#{1,6})\s+(.+)', line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            # Pop to correct parent
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else root
            if title not in parent:
                parent[title] = {}
            node = parent[title]
            if not isinstance(node, dict):
                node = {"content": [node]}
                parent[title] = node
            ensure_content(node)
            stack.append((level, node))
            i += 1
            continue

        # --- Table (lines starting with |) ---
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            if len(table_lines) >= 2:
                headers = [h.strip() for h in table_lines[0].strip("|").split("|")]
                rows = []
                for tl in table_lines[2:]:  # skip separator row
                    cells = [c.strip() for c in tl.strip("|").split("|")]
                    rows.append(cells)
                table = {
                    h: [row[j] if j < len(row) else "" for row in rows]
                    for j, h in enumerate(headers)
                }
                ensure_content(current_node()).append({"table": table})
            continue

        # --- Bullet / numbered list ---
        if re.match(r'^[\*\-]\s', line) or re.match(r'^\d+\.\s', line):
            bullets = []
            while i < len(lines) and (re.match(r'^[\*\-]\s', lines[i]) or re.match(r'^\d+\.\s', lines[i])):
                bullet_text = re.sub(r'^[\*\-\d]+\.?\s+', '', lines[i])
                bullets.append(bullet_text)
                i += 1
            ensure_content(current_node()).append(bullets)
            continue

        # --- HR or blank line ---
        if line.strip() == "" or re.match(r'^[-*]{3,}$', line.strip()):
            i += 1
            continue

        # --- Regular paragraph ---
        stripped = line.strip()
        if stripped:
            ensure_content(current_node()).append(stripped)
        i += 1

    return root


def simplify(node):
    """
    Match the TS generator's compaction:
    - node with only one content item and no child keys → return the item directly
    - otherwise keep as dict with content + children
    """
    if not isinstance(node, dict):
        return node

    children = {k: v for k, v in node.items() if k != "content"}
    content = node.get("content", [])

    if not content and not children:
        return {}

    if len(content) == 1 and not children:
        return content[0]

    result = {}
    if content:
        result["content"] = content
    for k, v in children.items():
        result[k] = simplify(v)
    return result


def convert_file(md_path: Path, json_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    parsed = parse_markdown(text)
    simplified = {k: simplify(v) for k, v in parsed.items()}
    json_path.write_text(json.dumps(simplified, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"  {md_path.name} → {json_path.name}")


FILES = [
    ("00", "legal"),
    ("01", "races"),
    ("02", "classes"),
    ("03", "beyond1st"),
    ("04", "equipment"),
    ("05", "feats"),
    ("06", "mechanics"),
    ("07", "combat"),
    ("08", "spellcasting"),
    ("09", "running"),
    ("10", "magic items"),
    ("11", "monsters"),
    ("12", "conditions"),
    ("13", "gods"),
    ("14", "planes"),
    ("15", "creatures"),
    ("16", "npcs"),
]


def main():
    JSON_DIR.mkdir(exist_ok=True)

    if len(sys.argv) >= 3:
        prefix, name = sys.argv[1], sys.argv[2]
        targets = [(prefix, name)]
    else:
        targets = FILES

    print(f"Regenerating {len(targets)} file(s)...")
    for prefix, name in targets:
        slug = f"{prefix} {name}"
        md_path = MD_DIR / f"{slug}.md"
        json_path = JSON_DIR / f"{slug}.json"
        if not md_path.exists():
            print(f"  SKIP (not found): {md_path.name}")
            continue
        convert_file(md_path, json_path)

    print("Done.")


if __name__ == "__main__":
    main()
