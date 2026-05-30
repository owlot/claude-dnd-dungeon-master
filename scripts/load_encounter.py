#!/usr/bin/env python3
"""
load_encounter.py — Print a structured DM summary of an encounter file.

Usage:
  python scripts/load_encounter.py <campaign> <encounter_name>

Reads: campaigns/<campaign>/encounters/<encounter_name>.md

Output sections (always in this order):
  1. ENCOUNTER header
  2. READ-ALOUD TEXT
  3. ENEMY STAT BLOCKS
  4. TERRAIN
  5. TACTICS
  6. REWARDS
"""

import os
import re
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "campaigns")

WIDTH = 60   # box inner width


# ── box drawing helpers ───────────────────────────────────────────────────────

def box_top(title: str = "", width: int = WIDTH) -> str:
    if title:
        t = f" {title} "
        pad = width - len(t)
        left = pad // 2
        right = pad - left
        return "╔" + "═" * left + t + "═" * right + "╗"
    return "╔" + "═" * (width + 2) + "╗"


def box_mid(width: int = WIDTH) -> str:
    return "╠" + "═" * (width + 2) + "╣"


def box_bot(width: int = WIDTH) -> str:
    return "╚" + "═" * (width + 2) + "╝"


def box_row(text: str, width: int = WIDTH) -> str:
    if len(text) > width:
        text = text[: width - 1] + "…"
    return "║ " + text.ljust(width) + " ║"


def box_blank(width: int = WIDTH) -> str:
    return "║ " + " " * width + " ║"


def wrap(text: str, width: int = WIDTH) -> list[str]:
    """Word-wrap text to fit within width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


# ── markdown helpers ──────────────────────────────────────────────────────────

def get_section_lines(lines: list[str], heading: str) -> list[str]:
    """Return all lines from the given ## heading until the next ## heading or EOF."""
    collecting = False
    result: list[str] = []
    heading_lower = heading.lower().strip()
    for line in lines:
        if line.startswith("## "):
            current = line.lstrip("# ").strip().lower()
            if current == heading_lower:
                collecting = True
                continue
            elif collecting:
                break
        elif collecting:
            result.append(line.rstrip("\n"))
    return result


def parse_key_value_table(lines: list[str]) -> list[tuple[str, str]]:
    """
    Parse a markdown two-column key/value table:
      | **Key** | Value |
    Returns list of (key, value) tuples.
    Stops after the first table (blank line or non-table line after rows).
    """
    pairs: list[tuple[str, str]] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break   # end of first table
            continue
        in_table = True
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cols) < 2:
            continue
        key = re.sub(r"\*+", "", cols[0]).strip()
        val = cols[1].strip()
        if not key or re.match(r"^[-: ]+$", key):
            continue
        if key.lower() in ("field", "key", "name"):
            continue
        pairs.append((key, val))
    return pairs


def parse_multi_col_table(lines: list[str], start_keyword: str) -> list[dict]:
    """
    Find the first markdown table after a line containing start_keyword.
    Returns list of dicts keyed by lowercase column header.
    """
    in_section = False
    header: list[str] = []
    rows: list[dict] = []
    for line in lines:
        if not in_section:
            if start_keyword.lower() in line.lower():
                in_section = True
            continue
        stripped = line.strip()
        if not stripped:
            if rows:
                break
            continue
        if not stripped.startswith("|"):
            if rows or header:
                break
            continue
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if not header:
            header = [re.sub(r"\*+", "", c).strip().lower() for c in cols]
            continue
        if all(re.match(r"^[-: ]+$", c) for c in cols if c):
            continue
        if len(cols) < len(header):
            cols += [""] * (len(header) - len(cols))
        rows.append({header[i]: cols[i] for i in range(len(header))})
    return rows


def extract_blockquote(lines: list[str]) -> list[str]:
    """Extract lines that are inside > blockquotes."""
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">"):
            content = stripped.lstrip("> ").strip()
            # Strip italic markdown
            content = re.sub(r"\*([^*]+)\*", r"\1", content)
            if content:
                result.append(content)
    return result


def extract_bullet_value(lines: list[str], key: str) -> str | None:
    """
    Find **Key:** or **Key**: value pattern anywhere in the line list.
    Handles colon inside bold (**Key:**) or outside (**Key**:).
    Matches both bullet lines and standalone bold-label lines.
    """
    # Colon may be inside (**Key:**) or outside (**Key**:) the bold markers
    pattern = re.compile(
        r"\*\*" + re.escape(key) + r":?\*\*:?\s*(.+)",
        re.IGNORECASE,
    )
    for line in lines:
        m = pattern.search(line)
        if m:
            return m.group(1).strip()
    return None


# ── section renderers ─────────────────────────────────────────────────────────

def render_header(all_lines: list[str], title: str) -> list[str]:
    """Section 1: Encounter header table (the key/value block before the first ---)."""
    # Only look at lines between the H1 title and the first horizontal rule
    header_lines: list[str] = []
    past_h1 = False
    for line in all_lines:
        if not past_h1:
            if line.startswith("# "):
                past_h1 = True
            continue
        if line.strip() == "---":
            break
        header_lines.append(line)

    pairs = parse_key_value_table(header_lines)
    out = [box_top("ENCOUNTER"), box_row(f"  {title}")]
    out.append(box_mid())
    for key, val in pairs:
        if not val or val.startswith("["):
            continue
        out.append(box_row(f"  {key:<20} {val}"))
    out.append(box_bot())
    return out


def render_read_aloud(all_lines: list[str]) -> list[str]:
    """Section 2: Boxed read-aloud text."""
    section = get_section_lines(all_lines, "Description / Read-Aloud Text")
    text_lines = extract_blockquote(section)
    if not text_lines:
        # Fall through to plain paragraph text
        for line in section:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("|") and not stripped.startswith("-") and not stripped.startswith(">") and not stripped.startswith("["):
                text_lines.extend(wrap(stripped))

    out = [box_top("READ ALOUD"), box_blank()]
    for sentence in text_lines:
        for wline in wrap(sentence):
            out.append(box_row(f"  {wline}"))
    out.append(box_blank())
    out.append(box_bot())
    return out


def render_enemies(all_lines: list[str]) -> list[str]:
    """Section 3: Enemy stat blocks."""
    enemies = parse_multi_col_table(all_lines, "## Enemies")
    attacks = parse_multi_col_table(all_lines, "### Attack Details")
    abilities_section = get_section_lines(all_lines, "Special Abilities & Conditions")

    # Group attacks by enemy name
    attacks_by_enemy: dict[str, list[dict]] = {}
    for atk in attacks:
        ename = atk.get("enemy", "").strip()
        if ename and not ename.startswith("["):
            attacks_by_enemy.setdefault(ename, []).append(atk)

    # Group abilities by enemy name
    abilities_by_enemy: dict[str, list[str]] = {}
    for line in abilities_section:
        m = re.match(r"[-*]\s+\*\*([^—–]+)[—–]([^:]+):\*\*\s*(.*)", line)
        if m:
            ename = m.group(1).strip()
            ability = f"{m.group(2).strip()}: {m.group(3).strip()}"
            abilities_by_enemy.setdefault(ename, []).append(ability)

    out = [box_top("ENEMY STAT BLOCKS")]
    any_enemy = False
    for enemy in enemies:
        name = enemy.get("name", "").strip()
        if not name or name.startswith("["):
            continue
        any_enemy = True
        count = enemy.get("count", "1")
        hp = enemy.get("hp each", "?")
        ac = enemy.get("ac", "?")
        speed = enemy.get("speed", "?")
        init = enemy.get("initiative", "?")

        out.append(box_mid())
        out.append(box_row(f"  {name.upper()}  (x{count})"))
        out.append(box_row(f"    HP: {hp}   AC: {ac}   Speed: {speed}   Init: {init}"))

        # Attacks
        for atk in attacks_by_enemy.get(name, []):
            atk_name = atk.get("attack name", atk.get("name", "?"))
            bonus = atk.get("attack bonus", "?")
            dmg = atk.get("damage", "?")
            dtype = atk.get("type", "")
            special = atk.get("special", "")
            atk_line = f"    Attack — {atk_name}: {bonus} to hit, {dmg} {dtype}"
            if special and not special.startswith("["):
                atk_line += f" [{special}]"
            for wline in wrap(atk_line):
                out.append(box_row(wline))

        # Special abilities
        for ability in abilities_by_enemy.get(name, []):
            for wline in wrap(f"    Ability — {ability}"):
                out.append(box_row(wline))

    if not any_enemy:
        out.append(box_row("  (No enemies listed)"))
    out.append(box_bot())
    return out


def parse_table_from_lines(lines: list[str]) -> list[dict]:
    """
    Parse the first markdown table found in the given lines (no section search needed).
    Returns a list of dicts keyed by lowercase column header.
    """
    header: list[str] = []
    rows: list[dict] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if not header:
            header = [re.sub(r"\*+", "", c).strip().lower() for c in cols]
            continue
        if all(re.match(r"^[-: ]+$", c) for c in cols if c):
            continue
        if len(cols) < len(header):
            cols += [""] * (len(header) - len(cols))
        rows.append({header[i]: cols[i] for i in range(len(header))})
    return rows


def render_terrain(all_lines: list[str]) -> list[str]:
    """Section 4: Terrain table."""
    section = get_section_lines(all_lines, "Terrain & Environmental Features")
    rows = parse_table_from_lines(section)

    # Also grab lighting and map notes — they appear as **Key:** value lines
    lighting = extract_bullet_value(section, "Lighting")
    map_notes = extract_bullet_value(section, "Map Notes")

    out = [box_top("TERRAIN")]
    any_row = False
    for row in rows:
        feature = row.get("feature", "").strip()
        if not feature or feature.startswith("["):
            continue
        any_row = True
        desc = row.get("description", "")
        effect = row.get("mechanical effect", row.get("effect", ""))
        out.append(box_row(f"  {feature}"))
        if desc and not desc.startswith("["):
            for wline in wrap(f"    {desc}"):
                out.append(box_row(wline))
        if effect and not effect.startswith("["):
            for wline in wrap(f"    Effect: {effect}"):
                out.append(box_row(wline))
        out.append(box_blank())

    if not any_row:
        out.append(box_row("  (No terrain features listed)"))
        out.append(box_blank())

    if lighting and not lighting.startswith("["):
        out.append(box_row(f"  Lighting: {lighting}"))
    if map_notes and not map_notes.startswith("["):
        for wline in wrap(f"  Map: {map_notes}"):
            out.append(box_row(wline))

    out.append(box_bot())
    return out


def render_tactics(all_lines: list[str]) -> list[str]:
    """Section 5: Tactics."""
    section = get_section_lines(all_lines, "Tactics")
    keys = ["Opening move", "Priority targets",
            "When bloodied (below half HP)", "Morale"]
    out = [box_top("TACTICS")]
    any_tactic = False
    for key in keys:
        val = extract_bullet_value(section, key)
        if val and not val.startswith("["):
            any_tactic = True
            short_key = key.split("(")[0].strip()
            out.append(box_row(f"  {short_key}:"))
            for wline in wrap(f"    {val}"):
                out.append(box_row(wline))
            out.append(box_blank())
    if not any_tactic:
        out.append(box_row("  (No tactics listed)"))
    out.append(box_bot())
    return out


def render_rewards(all_lines: list[str]) -> list[str]:
    """Section 6: Rewards."""
    section = get_section_lines(all_lines, "Rewards")
    loot = parse_multi_col_table(section, "### Loot")
    xp_rows = parse_multi_col_table(section, "### XP")

    out = [box_top("REWARDS")]
    out.append(box_row("  LOOT"))
    any_loot = False
    for row in loot:
        item = row.get("item", "").strip()
        if not item or item.startswith("["):
            continue
        any_loot = True
        source = row.get("source", "")
        notes = row.get("notes", "")
        loot_line = f"    {item}"
        if source and not source.startswith("["):
            loot_line += f" ({source})"
        if notes and not notes.startswith("["):
            loot_line += f" — {notes}"
        for wline in wrap(loot_line):
            out.append(box_row(wline))
    if not any_loot:
        out.append(box_row("    (No loot listed)"))

    out.append(box_blank())
    out.append(box_row("  XP"))
    any_xp = False
    for row in xp_rows:
        enemy = row.get("enemy", "").strip()
        if not enemy or enemy.startswith("[") or enemy.startswith("**"):
            # Catch total/per-character rows
            if enemy.startswith("**Per Character"):
                per_char = row.get("total", "?").strip("* ")
                out.append(box_row(f"    Per Character: {per_char} XP"))
            continue
        any_xp = True
        xp_each = row.get("xp each", "?")
        count = row.get("count", "?")
        total = row.get("total", "?")
        out.append(box_row(f"    {enemy}: {xp_each} XP x{count} = {total}"))
    if not any_xp:
        out.append(box_row("    (No XP listed)"))

    out.append(box_bot())
    return out


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    campaign, encounter_name = args[0], args[1]
    enc_path = os.path.join(BASE, campaign, "encounters", f"{encounter_name}.md")

    if not os.path.exists(enc_path):
        sys.exit(f"Error: encounter file not found: {enc_path}")

    with open(enc_path) as f:
        raw_lines = f.readlines()

    all_lines = [l.rstrip("\n") for l in raw_lines]

    # Extract title from first heading
    title = encounter_name
    for line in all_lines:
        m = re.match(r"^#\s+(.+)", line)
        if m:
            title = m.group(1).strip()
            break

    sections = [
        render_header(all_lines, title),
        render_read_aloud(all_lines),
        render_enemies(all_lines),
        render_terrain(all_lines),
        render_tactics(all_lines),
        render_rewards(all_lines),
    ]

    output_lines: list[str] = []
    for section in sections:
        output_lines.extend(section)
        output_lines.append("")   # blank line between sections

    print("\n".join(output_lines))


if __name__ == "__main__":
    main()
