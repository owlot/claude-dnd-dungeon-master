#!/usr/bin/env python3
"""
update_character.py — Update a character sheet in-place with a single patch command.

Usage:
  python scripts/update_character.py <campaign> <character_name> <patch_type> [value]

HP changes:
  hp <N>        — set Current HP to N (clamped 0..HP Maximum)
  damage <N>    — subtract N from Current HP
  heal <N>      — add N to Current HP (cap at HP Maximum)
  temp_hp <N>   — set Temporary HP to N

Death saves:
  death_success — increment death save successes (max 3, at 3 prints "STABLE")
  death_fail    — increment death save failures (max 3, at 3 prints "CHARACTER DEAD")
  death_reset   — reset both to 0

Spell slots:
  slot_use <level>      — decrement remaining slots at that level
  slot_restore <level>  — increment remaining slots (cap at total)
  slots_restore_all     — set all Remaining equal to Total

Class features / resources:
  feature_use <name>      — decrement use counter for named feature
  feature_restore <name>  — increment use counter (cap at max)
  features_restore_all    — restore all features to max uses

Conditions:
  condition_add <condition>    — add a condition to Notes
  condition_remove <condition> — remove a condition from Notes
  condition_clear              — clear all conditions

Gold:
  gold <N>      — set gold to N
  gold_add <N>  — add N gold
  gold_spend <N>— subtract N gold (warns if negative)

Hit dice:
  hd_use <N>      — decrement remaining hit dice by N
  hd_restore_all  — restore all hit dice
"""

import os
import re
import shutil
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "campaigns")

ORDINAL_TO_NUM = {
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "6th": 6, "7th": 7, "8th": 8, "9th": 9,
}
NUM_TO_ORDINAL = {v: k for k, v in ORDINAL_TO_NUM.items()}


# ── file finding ──────────────────────────────────────────────────────────────

def find_character_file(campaign: str, character_name: str) -> str:
    """
    Locate a character .md file. Tries exact filename match first
    (lowercased, spaces→underscores), then partial match.
    """
    char_dir = os.path.join(BASE, campaign, "characters")
    if not os.path.isdir(char_dir):
        sys.exit(f"Error: characters directory not found: {char_dir}")

    all_md = [
        f for f in os.listdir(char_dir)
        if f.endswith(".md") and not f.startswith("_") and not f.startswith(".")
    ]
    if not all_md:
        sys.exit(f"Error: no character files found in {char_dir}")

    # Exact filename match (lowercased, spaces→underscores)
    normalized = character_name.lower().replace(" ", "_")
    exact = normalized + ".md"
    if exact in [f.lower() for f in all_md]:
        for f in all_md:
            if f.lower() == exact:
                return os.path.join(char_dir, f)

    # Partial match against filename stem or heading inside file
    matches = []
    needle = character_name.lower()
    for fname in all_md:
        stem = fname[:-3].lower()
        if needle in stem:
            matches.append(fname)
            continue
        # Also check the # heading inside the file
        fpath = os.path.join(char_dir, fname)
        try:
            with open(fpath) as fh:
                for line in fh:
                    m = re.match(r"^#\s+(.+)", line)
                    if m:
                        heading = m.group(1).strip().lower()
                        if needle in heading:
                            matches.append(fname)
                        break
        except OSError:
            pass

    # Deduplicate preserving order
    seen = set()
    matches = [x for x in matches if not (x in seen or seen.add(x))]

    if len(matches) == 0:
        sys.exit(
            f"Error: no character matching '{character_name}' found in {char_dir}\n"
            f"Available: {', '.join(f[:-3] for f in all_md)}"
        )
    if len(matches) > 1:
        sys.exit(
            f"Error: ambiguous character name '{character_name}' — matches:\n"
            + "\n".join(f"  {f[:-3]}" for f in matches)
        )
    return os.path.join(char_dir, matches[0])


def get_character_name(content: str, filepath: str) -> str:
    for line in content.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            candidate = m.group(1).strip()
            if not candidate.startswith("["):
                return candidate
    return os.path.basename(filepath)[:-3]


# ── combat stat helpers ───────────────────────────────────────────────────────

def parse_combat_stat(content: str, label: str):
    """Return the raw value string from | **Label** | value | row."""
    pattern = re.compile(
        r"(\|\s*\*\*" + re.escape(label) + r"\*\*\s*\|\s*)([^|]+?)(\s*\|)",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    return m if m else None


def get_combat_int(content: str, label: str) -> int:
    m = parse_combat_stat(content, label)
    if m is None:
        return 0
    try:
        return int(m.group(2).strip())
    except ValueError:
        return 0


def set_combat_stat(content: str, label: str, new_value) -> str:
    """Replace the value in a | **Label** | value | row."""
    pattern = re.compile(
        r"(\|\s*\*\*" + re.escape(label) + r"\*\*\s*\|\s*)([^|]+?)(\s*\|)",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    if m is None:
        sys.exit(f"Error: could not find '{label}' field in character file.")
    return content[: m.start(2)] + str(new_value) + content[m.end(2):]


# ── death saves ───────────────────────────────────────────────────────────────

def parse_death_saves(content: str) -> tuple[int, int]:
    """Return (successes, failures)."""
    pattern = re.compile(
        r"\|\s*\*\*Death Saves\*\*\s*\|\s*Successes:\s*(\d+)\s*/\s*Failures:\s*(\d+)\s*\|",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def set_death_saves(content: str, successes: int, failures: int) -> str:
    pattern = re.compile(
        r"(\|\s*\*\*Death Saves\*\*\s*\|\s*)Successes:\s*\d+\s*/\s*Failures:\s*\d+(\s*\|)",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    if m is None:
        sys.exit("Error: could not find 'Death Saves' field in character file.")
    replacement = f"{m.group(1)}Successes: {successes} / Failures: {failures}{m.group(2)}"
    return content[: m.start()] + replacement + content[m.end():]


# ── spell slots ───────────────────────────────────────────────────────────────

def parse_spell_slot_row(content: str, level_label: str) -> tuple[int, int] | None:
    """
    Return (total, remaining) for the given ordinal level label (e.g. '1st').
    Looks in the ### Spell Slots table.
    """
    lines = content.splitlines()
    in_spell_table = False
    for line in lines:
        if "### Spell Slots" in line or "### Pact Magic Slots" in line:
            in_spell_table = True
            continue
        if in_spell_table:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue   # skip blank lines, blockquotes, notes before the table
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 3:
                continue
            if cols[0].lower() == level_label.lower():
                try:
                    return int(cols[1]), int(cols[2])
                except ValueError:
                    return None
    return None


def set_spell_slot_remaining(content: str, level_label: str, new_remaining: int) -> str:
    """
    Replace the Remaining column value for the given level in the Spell Slots table.
    The row looks like: | 2nd | 3 | 2 |
    We want to replace only the Remaining column (3rd column) for that specific level.
    """
    lines = content.splitlines()
    in_spell_table = False
    result_lines = []
    for line in lines:
        if "### Spell Slots" in line or "### Pact Magic Slots" in line:
            in_spell_table = True
            result_lines.append(line)
            continue
        if in_spell_table:
            stripped = line.strip()
            if not stripped.startswith("|"):
                result_lines.append(line)
                continue   # skip blank lines and non-table lines (e.g. blockquotes)
            cols_raw = stripped.strip("|").split("|")
            cols = [c.strip() for c in cols_raw]
            if len(cols) >= 3 and cols[0].lower() == level_label.lower():
                # Rebuild the row replacing the 3rd column (Remaining)
                # Preserve whitespace in the original columns
                new_line = (
                    "| "
                    + cols[0] + " | "
                    + cols[1] + " | "
                    + str(new_remaining) + " |"
                )
                result_lines.append(new_line)
                in_spell_table = False  # one match only
                continue
        result_lines.append(line)
    return "\n".join(result_lines)


def get_all_spell_slots(content: str) -> list[tuple[str, int, int]]:
    """Return list of (level_label, total, remaining) for all slot rows."""
    lines = content.splitlines()
    in_spell_table = False
    slots = []
    for line in lines:
        if "### Spell Slots" in line or "### Pact Magic Slots" in line:
            in_spell_table = True
            continue
        if in_spell_table:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue   # skip blank lines and non-table lines (e.g. blockquotes)
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 3:
                continue
            if cols[0].startswith("[") or all(re.match(r"^[-: ]+$", c) for c in cols if c):
                continue
            try:
                slots.append((cols[0], int(cols[1]), int(cols[2])))
            except (ValueError, IndexError):
                continue
    return slots


def restore_all_spell_slots(content: str) -> str:
    """Set all Remaining equal to Total in the Spell Slots table."""
    slots = get_all_spell_slots(content)
    for level_label, total, _remaining in slots:
        content = set_spell_slot_remaining(content, level_label, total)
    return content


# ── class features ────────────────────────────────────────────────────────────

FEAT_PATTERN = re.compile(
    r"\*\*([^*(]+?)\s*\((\d+)\s*/\s*(\d+)(?:\s*uses?)?\):?\*\*",
    re.IGNORECASE,
)


def find_feature(content: str, name_fragment: str) -> re.Match | None:
    """Find the first feature match whose name contains name_fragment (case-insensitive)."""
    needle = name_fragment.lower()
    for m in FEAT_PATTERN.finditer(content):
        if needle in m.group(1).strip().lower():
            return m
    return None


def set_feature_uses(content: str, match: re.Match, new_current: int) -> str:
    """Replace the (X/Y) part of a feature match."""
    old = match.group(0)
    feat_name = match.group(1)
    max_uses = match.group(3)
    # Preserve whether it said "uses" in the original
    uses_word = ""
    if "uses" in match.group(0).lower()[match.group(0).lower().index("("):]:
        uses_word = " uses"
    # Check for trailing colon before **
    has_colon = ":)**" in old or ": )**" in old or old.rstrip().endswith(":)**")
    # Reconstruct: **Name (X/Y uses):** or **Name (X/Y)**
    # Detect colon position from original
    after_paren = old[old.rindex(")") + 1:]  # e.g. ":** or ")**"
    new = f"**{feat_name}({new_current}/{max_uses}{uses_word}){after_paren}"
    return content[: match.start()] + new + content[match.end():]


def restore_all_features(content: str) -> str:
    """Set all feature current uses equal to max."""
    # Process in reverse order so offsets remain valid
    matches = list(FEAT_PATTERN.finditer(content))
    for m in reversed(matches):
        max_uses = int(m.group(3))
        content = set_feature_uses(content, m, max_uses)
    return content


# ── conditions ────────────────────────────────────────────────────────────────

def parse_conditions(content: str) -> list[str]:
    notes_section = ""
    in_notes = False
    for line in content.splitlines():
        if re.match(r"^##\s+Notes", line, re.IGNORECASE):
            in_notes = True
            continue
        if in_notes:
            if line.startswith("## "):
                break
            notes_section += line + "\n"
    m = re.search(r"[Cc]onditions?[:\s]+(.+)", notes_section)
    if m:
        raw = m.group(1).strip().rstrip(".")
        none_like = {"none", "—", "-", "", "n/a", "normal", "clear"}
        if raw.lower() in none_like:
            return []
        return [
            c.strip().rstrip(".")
            for c in re.split(r"[,;]", raw)
            if c.strip().rstrip(".").lower() not in none_like
        ]
    return []


def set_conditions(content: str, conditions: list[str]) -> str:
    """
    Set the Conditions line in the Notes section.
    If there's already a Conditions: line, replace it.
    Otherwise append it to the Notes section.
    """
    cond_str = ", ".join(conditions) if conditions else "None"

    # Try to replace existing Conditions: line
    cond_line_pattern = re.compile(r"([Cc]onditions?[:\s]+).+", re.MULTILINE)
    m = cond_line_pattern.search(content)
    if m:
        new_line = m.group(1) + cond_str
        return content[: m.start()] + new_line + content[m.end():]

    # Otherwise, find the Notes section and append
    notes_pattern = re.compile(r"(^##\s+Notes[^\n]*\n)", re.IGNORECASE | re.MULTILINE)
    nm = notes_pattern.search(content)
    if nm:
        insert_pos = nm.end()
        return content[:insert_pos] + f"Conditions: {cond_str}\n\n" + content[insert_pos:]

    # No Notes section — append at end
    return content.rstrip("\n") + f"\n\n## Notes\n\nConditions: {cond_str}\n"


# ── gold ──────────────────────────────────────────────────────────────────────

def parse_gold(content: str) -> int:
    """Parse Gold (gp) from the Currency table."""
    m = re.search(
        r"\|\s*Gold\s*\(gp\)\s*\|\s*(\d+)\s*\|",
        content,
        re.IGNORECASE,
    )
    return int(m.group(1)) if m else 0


def set_gold(content: str, new_amount: int) -> str:
    pattern = re.compile(
        r"(\|\s*Gold\s*\(gp\)\s*\|\s*)(\d+)(\s*\|)",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    if m is None:
        sys.exit("Error: could not find 'Gold (gp)' row in Currency table.")
    return content[: m.start(2)] + str(new_amount) + content[m.end(2):]


# ── hit dice ──────────────────────────────────────────────────────────────────

def parse_hit_dice(content: str) -> tuple[str, int, int]:
    """
    Parse Hit Dice row: | **Hit Dice** | 3d10 (remaining: 2) |
    Returns (dice_type, total, remaining).
    """
    m = re.search(
        r"\|\s*\*\*Hit Dice\*\*\s*\|\s*(\d+)(d\d+)\s*\(remaining:\s*(\d+)\)\s*\|",
        content,
        re.IGNORECASE,
    )
    if m:
        total = int(m.group(1))
        dice_type = m.group(1) + m.group(2)
        remaining = int(m.group(3))
        return dice_type, total, remaining
    return ("?", 0, 0)


def set_hit_dice_remaining(content: str, new_remaining: int) -> str:
    pattern = re.compile(
        r"(\|\s*\*\*Hit Dice\*\*\s*\|\s*\d+d\d+\s*\(remaining:\s*)(\d+)(\)\s*\|)",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    if m is None:
        sys.exit("Error: could not find 'Hit Dice' field in character file.")
    return content[: m.start(2)] + str(new_remaining) + content[m.end(2):]


# ── dispatch ──────────────────────────────────────────────────────────────────

def apply_patch(content: str, patch_type: str, value: str, char_name: str) -> tuple[str, str]:
    """
    Apply the requested patch to content. Returns (new_content, confirmation_message).
    """
    pt = patch_type.lower()

    # ── HP ────────────────────────────────────────────────────────────────────
    if pt in ("hp", "damage", "heal"):
        hp_max = get_combat_int(content, "HP Maximum")
        hp_old = get_combat_int(content, "Current HP")
        if not value:
            sys.exit(f"Error: '{patch_type}' requires a numeric value.")
        try:
            n = int(value)
        except ValueError:
            sys.exit(f"Error: invalid number '{value}'.")

        if pt == "hp":
            hp_new = max(0, min(hp_max, n))
            label = f"Current HP set to {hp_new}"
        elif pt == "damage":
            hp_new = max(0, hp_old - n)
            label = f"Current HP: {hp_old} → {hp_new} (took {n} damage)"
        else:  # heal
            hp_new = min(hp_max, hp_old + n)
            label = f"Current HP: {hp_old} → {hp_new} (healed {n})"

        new_content = set_combat_stat(content, "Current HP", hp_new)
        return new_content, f"✓ {char_name} — {label}"

    if pt == "temp_hp":
        if not value:
            sys.exit("Error: 'temp_hp' requires a numeric value.")
        try:
            n = int(value)
        except ValueError:
            sys.exit(f"Error: invalid number '{value}'.")
        new_content = set_combat_stat(content, "Temporary HP", n)
        return new_content, f"✓ {char_name} — Temporary HP set to {n}"

    # ── Death saves ───────────────────────────────────────────────────────────
    if pt == "death_success":
        succ, fail = parse_death_saves(content)
        if succ >= 3:
            return content, f"✓ {char_name} — already has 3 death save successes (STABLE)"
        succ += 1
        new_content = set_death_saves(content, succ, fail)
        extra = " — STABLE" if succ >= 3 else ""
        return new_content, f"✓ {char_name} — Death save successes: {succ}/3{extra}"

    if pt == "death_fail":
        succ, fail = parse_death_saves(content)
        if fail >= 3:
            return content, f"✓ {char_name} — already has 3 death save failures (CHARACTER DEAD)"
        fail += 1
        new_content = set_death_saves(content, succ, fail)
        extra = " — CHARACTER DEAD" if fail >= 3 else ""
        return new_content, f"✓ {char_name} — Death save failures: {fail}/3{extra}"

    if pt == "death_reset":
        new_content = set_death_saves(content, 0, 0)
        return new_content, f"✓ {char_name} — Death saves reset (0/0)"

    # ── Spell slots ───────────────────────────────────────────────────────────
    if pt == "slot_use":
        level_label = _parse_level_label(value)
        row = parse_spell_slot_row(content, level_label)
        if row is None:
            sys.exit(f"Error: no spell slot row found for level '{level_label}'.")
        total, remaining = row
        if remaining <= 0:
            return content, f"✓ {char_name} — no {level_label} level slots remaining (already 0)"
        new_remaining = remaining - 1
        new_content = set_spell_slot_remaining(content, level_label, new_remaining)
        return new_content, f"✓ {char_name} — {level_label} level slot used ({new_remaining}/{total} remaining)"

    if pt == "slot_restore":
        level_label = _parse_level_label(value)
        row = parse_spell_slot_row(content, level_label)
        if row is None:
            sys.exit(f"Error: no spell slot row found for level '{level_label}'.")
        total, remaining = row
        new_remaining = min(total, remaining + 1)
        new_content = set_spell_slot_remaining(content, level_label, new_remaining)
        return new_content, f"✓ {char_name} — {level_label} level slot restored ({new_remaining}/{total} remaining)"

    if pt == "slots_restore_all":
        new_content = restore_all_spell_slots(content)
        return new_content, f"✓ {char_name} — all spell slots restored"

    # ── Class features ────────────────────────────────────────────────────────
    if pt == "feature_use":
        if not value:
            sys.exit("Error: 'feature_use' requires a feature name.")
        m = find_feature(content, value)
        if m is None:
            sys.exit(f"Error: no feature matching '{value}' found.")
        feat_name = m.group(1).strip()
        current = int(m.group(2))
        max_uses = int(m.group(3))
        if current <= 0:
            return content, f"✓ {char_name} — {feat_name} already at 0 uses"
        new_current = current - 1
        new_content = set_feature_uses(content, m, new_current)
        return new_content, f"✓ {char_name} — {feat_name} used ({new_current}/{max_uses} remaining)"

    if pt == "feature_restore":
        if not value:
            sys.exit("Error: 'feature_restore' requires a feature name.")
        m = find_feature(content, value)
        if m is None:
            sys.exit(f"Error: no feature matching '{value}' found.")
        feat_name = m.group(1).strip()
        current = int(m.group(2))
        max_uses = int(m.group(3))
        new_current = min(max_uses, current + 1)
        new_content = set_feature_uses(content, m, new_current)
        return new_content, f"✓ {char_name} — {feat_name} restored ({new_current}/{max_uses} remaining)"

    if pt == "features_restore_all":
        new_content = restore_all_features(content)
        return new_content, f"✓ {char_name} — all features restored to max uses"

    # ── Conditions ────────────────────────────────────────────────────────────
    if pt == "condition_add":
        if not value:
            sys.exit("Error: 'condition_add' requires a condition name.")
        conditions = parse_conditions(content)
        if value.lower() not in [c.lower() for c in conditions]:
            conditions.append(value.capitalize())
        new_content = set_conditions(content, conditions)
        return new_content, f"✓ {char_name} — {value.capitalize()} condition added"

    if pt == "condition_remove":
        if not value:
            sys.exit("Error: 'condition_remove' requires a condition name.")
        conditions = parse_conditions(content)
        before = len(conditions)
        conditions = [c for c in conditions if c.lower() != value.lower()]
        if len(conditions) == before:
            return content, f"✓ {char_name} — condition '{value}' not found (no change)"
        new_content = set_conditions(content, conditions)
        return new_content, f"✓ {char_name} — {value.capitalize()} condition removed"

    if pt == "condition_clear":
        new_content = set_conditions(content, [])
        return new_content, f"✓ {char_name} — all conditions cleared"

    # ── Gold ──────────────────────────────────────────────────────────────────
    if pt == "gold":
        if not value:
            sys.exit("Error: 'gold' requires a numeric value.")
        try:
            n = int(value)
        except ValueError:
            sys.exit(f"Error: invalid number '{value}'.")
        new_content = set_gold(content, n)
        return new_content, f"✓ {char_name} — Gold set to {n} gp"

    if pt == "gold_add":
        if not value:
            sys.exit("Error: 'gold_add' requires a numeric value.")
        try:
            n = int(value)
        except ValueError:
            sys.exit(f"Error: invalid number '{value}'.")
        old_gold = parse_gold(content)
        new_gold = old_gold + n
        new_content = set_gold(content, new_gold)
        return new_content, f"✓ {char_name} — Gold: {old_gold} → {new_gold} gp (added {n})"

    if pt == "gold_spend":
        if not value:
            sys.exit("Error: 'gold_spend' requires a numeric value.")
        try:
            n = int(value)
        except ValueError:
            sys.exit(f"Error: invalid number '{value}'.")
        old_gold = parse_gold(content)
        new_gold = old_gold - n
        if new_gold < 0:
            print(f"Warning: {char_name} would go into debt ({new_gold} gp).", file=sys.stderr)
        new_content = set_gold(content, new_gold)
        return new_content, f"✓ {char_name} — Gold: {old_gold} → {new_gold} gp (spent {n})"

    # ── Hit dice ──────────────────────────────────────────────────────────────
    if pt == "hd_use":
        if not value:
            sys.exit("Error: 'hd_use' requires a numeric value.")
        try:
            n = int(value)
        except ValueError:
            sys.exit(f"Error: invalid number '{value}'.")
        dice_type, total, remaining = parse_hit_dice(content)
        new_remaining = max(0, remaining - n)
        new_content = set_hit_dice_remaining(content, new_remaining)
        return new_content, f"✓ {char_name} — Hit dice: {new_remaining}/{total} remaining"

    if pt == "hd_restore_all":
        dice_type, total, remaining = parse_hit_dice(content)
        new_content = set_hit_dice_remaining(content, total)
        return new_content, f"✓ {char_name} — Hit dice fully restored ({total}/{total})"

    sys.exit(
        f"Error: unknown patch type '{patch_type}'.\n"
        f"Run with --help or see the module docstring for valid patch types."
    )


def _parse_level_label(value: str) -> str:
    """
    Accept either ordinal ('2nd') or integer ('2') and return ordinal label.
    """
    if not value:
        sys.exit("Error: spell slot command requires a level (e.g. '2' or '2nd').")
    value = value.strip().lower()
    if value in ORDINAL_TO_NUM:
        return value
    try:
        n = int(value)
        if n in NUM_TO_ORDINAL:
            return NUM_TO_ORDINAL[n]
    except ValueError:
        pass
    # Maybe the user passed something like "2nd" already in our map
    sys.exit(f"Error: unrecognised spell level '{value}'. Use 1–9 or '1st', '2nd', etc.")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if len(args) < 3 or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if args and args[0] in ("-h", "--help") else 1)

    campaign = args[0]
    char_arg = args[1]
    patch_type = args[2]
    value = args[3] if len(args) > 3 else ""

    # Validate campaign directory
    campaign_path = os.path.join(BASE, campaign)
    if not os.path.isdir(campaign_path):
        sys.exit(f"Error: campaign directory not found: {campaign_path}")

    filepath = find_character_file(campaign, char_arg)

    with open(filepath) as f:
        content = f.read()

    char_name = get_character_name(content, filepath)
    new_content, msg = apply_patch(content, patch_type, value, char_name)

    if new_content != content:
        shutil.copy2(filepath, filepath + ".bak")
        with open(filepath, "w") as f:
            f.write(new_content)

    print(msg)


if __name__ == "__main__":
    main()
