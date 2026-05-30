#!/usr/bin/env python3
"""
party_status.py — Show current party HP, conditions, spell slots, and resources.

Usage:
  python scripts/party_status.py <campaign>

Reads all files in campaigns/<campaign>/characters/*.md and produces a
formatted party status block.
"""

import os
import re
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "campaigns")

WIDTH = 60   # inner content width


# ── box helpers ───────────────────────────────────────────────────────────────

def box_top(width: int = WIDTH) -> str:
    return "╔" + "═" * (width + 2) + "╗"


def box_mid(width: int = WIDTH) -> str:
    return "╠" + "═" * (width + 2) + "╣"


def box_bot(width: int = WIDTH) -> str:
    return "╚" + "═" * (width + 2) + "╝"


def box_row(text: str, width: int = WIDTH) -> str:
    if len(text) > width:
        text = text[: width - 1] + "…"
    return "║  " + text.ljust(width) + "  ║"


def sep(width: int = WIDTH) -> str:
    return "║  " + "─" * width + "  ║"


# ── character file parser ─────────────────────────────────────────────────────

def parse_combat_stat(content: str, label: str) -> int | None:
    """
    Extract the integer value from a table row like:
      | **Armor Class** | 15 |
    """
    pattern = re.compile(
        r"\|\s*\*\*" + re.escape(label) + r"\*\*\s*\|\s*(\d+)",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    return int(m.group(1)) if m else None


def parse_character_file(filepath: str) -> dict:
    with open(filepath) as f:
        content = f.read()

    lines = content.splitlines()

    # Character name from first # heading
    name = os.path.basename(filepath)[:-3]
    for line in lines:
        m = re.match(r"^#\s+(.+)", line)
        if m:
            candidate = m.group(1).strip()
            # skip template placeholder
            if not candidate.startswith("["):
                name = candidate
            break

    warnings: list[str] = []

    hp_max_val = parse_combat_stat(content, "HP Maximum")
    if hp_max_val is None:
        warnings.append("missing HP Maximum field")
    hp_max = hp_max_val or 0

    hp_current = parse_combat_stat(content, "Current HP")
    if hp_current is None:
        warnings.append("missing Current HP field")
        hp_current = hp_max

    ac_val = parse_combat_stat(content, "Armor Class")
    if ac_val is None:
        warnings.append("missing Armor Class field")
    ac = ac_val or 10

    if warnings:
        fname = os.path.basename(filepath)
        for w in warnings:
            print(f"Warning: {fname}: {w}", file=sys.stderr)

    # Conditions from Notes section (free-text section at the bottom)
    conditions: list[str] = []
    notes_section = ""
    in_notes = False
    for line in lines:
        if re.match(r"^##\s+Notes", line, re.IGNORECASE):
            in_notes = True
            continue
        if in_notes:
            if line.startswith("## "):
                break
            notes_section += line + "\n"

    # Look for Condition: or Conditions: in notes
    cond_match = re.search(r"[Cc]onditions?[:\s]+(.+)", notes_section)
    if cond_match:
        raw = cond_match.group(1).strip().rstrip(".")
        none_like = {"none", "—", "-", "", "n/a", "normal", "clear"}
        if raw.lower() not in none_like:
            conditions = [
                c.strip().rstrip(".")
                for c in re.split(r"[,;]", raw)
                if c.strip().rstrip(".").lower() not in none_like
            ]

    # Also check Party Status table in state.md (not here — we read chars only)

    # Spell slots — parse the ### Spell Slots table
    # | Level | Total | Remaining |
    spell_slots: list[tuple[str, int, int]] = []
    in_spell_table = False
    spell_header: list[str] = []
    for line in lines:
        if "### Spell Slots" in line or "### Pact Magic Slots" in line:
            in_spell_table = True
            spell_header = []
            continue
        if in_spell_table:
            stripped = line.strip()
            if not stripped:
                if spell_slots:
                    break
                continue
            if not stripped.startswith("|"):
                if spell_slots:
                    break
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if not spell_header:
                spell_header = [c.lower() for c in cols]
                continue
            if all(re.match(r"^[-: ]+$", c) for c in cols if c):
                continue
            if len(cols) < 3:
                continue
            level_label = cols[0]
            if level_label.startswith("[") or not level_label:
                continue
            try:
                total = int(cols[1])
                remaining = int(cols[2])
                spell_slots.append((level_label, total, remaining))
            except (ValueError, IndexError):
                continue

    # Class features with (X/Y uses) pattern
    # e.g. "**Action Surge (1/1 uses):** ..."
    # or   "**Second Wind (0/1):**"
    features: list[tuple[str, int, int]] = []
    # Matches **Feature Name (X/Y uses):** or **Feature Name (X/Y)**
    feat_pattern = re.compile(
        r"\*\*([^*(]+?)\s*\((\d+)\s*/\s*(\d+)(?:\s*uses?)?\):?\*\*",
        re.IGNORECASE,
    )
    for m in feat_pattern.finditer(content):
        feat_name = m.group(1).strip()
        current_uses = int(m.group(2))
        max_uses = int(m.group(3))
        features.append((feat_name, current_uses, max_uses))

    return {
        "name": name,
        "hp_current": hp_current,
        "hp_max": hp_max,
        "ac": ac,
        "conditions": conditions,
        "spell_slots": spell_slots,
        "features": features,
    }


# ── renderer ──────────────────────────────────────────────────────────────────

def render_party(characters: list[dict]) -> str:
    lines: list[str] = [box_top(), box_row("PARTY STATUS"), box_mid()]
    lines.append(box_row("NAME           HP         AC   CONDITIONS"))
    lines.append(sep())

    for char in characters:
        name = char["name"][:14].ljust(14)
        hp_str = f"{char['hp_current']}/{char['hp_max']}".ljust(10)
        ac_str = str(char["ac"]).ljust(4)
        conds = ", ".join(char["conditions"]) if char["conditions"] else "—"
        line = f"{name} {hp_str} {ac_str} {conds}"
        lines.append(box_row(line))

    # Resources section
    any_resources = any(
        char["spell_slots"] or char["features"] for char in characters
    )
    if any_resources:
        lines.append(box_mid())
        lines.append(box_row("RESOURCES"))

        for char in characters:
            if not char["spell_slots"] and not char["features"]:
                continue

            parts: list[str] = []

            # Spell slots
            for level_label, total, remaining in char["spell_slots"]:
                parts.append(f"{level_label}: {remaining}/{total}")

            # Class features
            for feat_name, current_uses, max_uses in char["features"]:
                parts.append(f"{feat_name}: {current_uses}/{max_uses}")

            if parts:
                name_part = char["name"] + ":"
                resource_str = "  ".join(parts)
                full = f"{name_part:<12} {resource_str}"
                # Word wrap if needed
                if len(full) <= WIDTH:
                    lines.append(box_row(full))
                else:
                    lines.append(box_row(f"{name_part}"))
                    # Break parts into lines
                    current_line = "  "
                    for p in parts:
                        if len(current_line) + len(p) + 2 <= WIDTH:
                            current_line += p + "  "
                        else:
                            lines.append(box_row(current_line.rstrip()))
                            current_line = "  " + p + "  "
                    if current_line.strip():
                        lines.append(box_row(current_line.rstrip()))

    lines.append(box_bot())
    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    campaign = args[0]
    char_dir = os.path.join(BASE, campaign, "characters")

    if not os.path.isdir(os.path.join(BASE, campaign)):
        sys.exit(f"Error: campaign directory not found: {os.path.join(BASE, campaign)}")

    if not os.path.isdir(char_dir):
        sys.exit(f"Error: characters directory not found: {char_dir}")

    char_files = sorted(
        f for f in os.listdir(char_dir)
        if f.endswith(".md") and not f.startswith("_") and not f.startswith(".")
    )

    if not char_files:
        sys.exit(f"Error: no character files found in {char_dir}")

    characters: list[dict] = []
    for fname in char_files:
        fpath = os.path.join(char_dir, fname)
        try:
            char = parse_character_file(fpath)
            # Skip template placeholder files
            if char["name"].startswith("[") or char["hp_max"] == 0:
                continue
            characters.append(char)
        except Exception as e:
            print(f"Warning: could not parse {fname}: {e}", file=sys.stderr)

    if not characters:
        sys.exit("Error: no valid character files found (all appear to be templates).")

    print(render_party(characters))


if __name__ == "__main__":
    main()
