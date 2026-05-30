#!/usr/bin/env python3
"""
show_character.py — Display a clean, readable character sheet in a box.

Usage:
  python scripts/show_character.py <campaign> <character_name>

Sections always shown (in order):
  Header, COMBAT, ABILITY SCORES, SAVING THROWS, SKILLS,
  ATTACKS, SPELLCASTING (if applicable), RESOURCES (if applicable),
  CONDITIONS, INVENTORY
"""

import os
import re
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "campaigns")

WIDTH = 56  # inner content width (between the ║  and  ║)

ABILITY_NAMES = ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"]
ABILITY_SHORT = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

SKILL_TABLE = [
    ("Acrobatics",     "DEX"),
    ("Animal Handling","WIS"),
    ("Arcana",         "INT"),
    ("Athletics",      "STR"),
    ("Deception",      "CHA"),
    ("History",        "INT"),
    ("Insight",        "WIS"),
    ("Intimidation",   "CHA"),
    ("Investigation",  "INT"),
    ("Medicine",       "WIS"),
    ("Nature",         "INT"),
    ("Perception",     "WIS"),
    ("Performance",    "CHA"),
    ("Persuasion",     "CHA"),
    ("Religion",       "INT"),
    ("Sleight of Hand","DEX"),
    ("Stealth",        "DEX"),
    ("Survival",       "WIS"),
]


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


def wrap_row(text: str, width: int = WIDTH, indent: int = 0) -> list[str]:
    """Word-wrap text into multiple box rows."""
    prefix = " " * indent
    words = text.split()
    lines: list[str] = []
    current = prefix
    for word in words:
        if current == prefix:
            current += word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(box_row(current, width))
            current = prefix + word
    if current.strip():
        lines.append(box_row(current, width))
    return lines


# ── file finding (same logic as update_character.py) ─────────────────────────

def find_character_file(campaign: str, character_name: str) -> str:
    char_dir = os.path.join(BASE, campaign, "characters")
    if not os.path.isdir(char_dir):
        sys.exit(f"Error: characters directory not found: {char_dir}")

    all_md = [
        f for f in os.listdir(char_dir)
        if f.endswith(".md") and not f.startswith("_") and not f.startswith(".")
    ]
    if not all_md:
        sys.exit(f"Error: no character files found in {char_dir}")

    normalized = character_name.lower().replace(" ", "_")
    exact = normalized + ".md"
    if exact in [f.lower() for f in all_md]:
        for f in all_md:
            if f.lower() == exact:
                return os.path.join(char_dir, f)

    matches = []
    needle = character_name.lower()
    for fname in all_md:
        stem = fname[:-3].lower()
        if needle in stem:
            matches.append(fname)
            continue
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


# ── parsers ───────────────────────────────────────────────────────────────────

def get_character_name(content: str, filepath: str) -> str:
    for line in content.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            candidate = m.group(1).strip()
            if not candidate.startswith("["):
                return candidate
    return os.path.basename(filepath)[:-3]


def parse_info_table(content: str) -> dict[str, str]:
    """Parse the top-level | Field | Value | table."""
    result: dict[str, str] = {}
    for line in content.splitlines():
        m = re.match(r"\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            result[key] = val
    return result


def parse_combat_stat(content: str, label: str) -> str | None:
    pattern = re.compile(
        r"\|\s*\*\*" + re.escape(label) + r"\*\*\s*\|\s*([^|]+?)\s*\|",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    return m.group(1).strip() if m else None


def parse_combat_int(content: str, label: str) -> int:
    v = parse_combat_stat(content, label)
    if v is None:
        return 0
    try:
        return int(re.search(r"-?\d+", v).group())
    except (AttributeError, ValueError):
        return 0


def parse_ability_scores(content: str) -> dict[str, tuple[int, int]]:
    """Return {ability_name: (score, modifier)} for all 6 abilities."""
    result: dict[str, tuple[int, int]] = {}
    in_section = False
    for line in content.splitlines():
        if re.match(r"^##\s+Ability Scores", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 3:
                continue
            name = cols[0]
            if name in ABILITY_NAMES:
                try:
                    score = int(cols[1])
                    mod_str = cols[2]
                    # Modifier may be "+3" or "-1" or "3"
                    mod_m = re.search(r"([+-]?\d+)", mod_str)
                    mod = int(mod_m.group(1)) if mod_m else (score - 10) // 2
                    result[name] = (score, mod)
                except (ValueError, AttributeError):
                    pass
    return result


def parse_saving_throws(content: str) -> dict[str, tuple[int, bool]]:
    """Return {ability_name: (modifier, is_proficient)}."""
    result: dict[str, tuple[int, bool]] = {}
    in_section = False
    for line in content.splitlines():
        if re.match(r"^##\s+Saving Throws", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 3:
                continue
            name = cols[0]
            if name in ABILITY_NAMES:
                try:
                    mod_m = re.search(r"([+-]?\d+)", cols[1])
                    mod = int(mod_m.group(1)) if mod_m else 0
                    prof = "[x]" in cols[2].lower() or "x" in cols[2].lower()
                    result[name] = (mod, prof)
                except (ValueError, AttributeError):
                    pass
    return result


def parse_skills(content: str) -> dict[str, tuple[int, bool, bool]]:
    """Return {skill_name: (modifier, proficient, expertise)}."""
    result: dict[str, tuple[int, bool, bool]] = {}
    in_section = False
    for line in content.splitlines():
        if re.match(r"^##\s+Skills", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 5:
                continue
            name = cols[0]
            skill_names = [s for s, _ in SKILL_TABLE]
            if name in skill_names:
                try:
                    mod_m = re.search(r"([+-]?\d+)", cols[2])
                    mod = int(mod_m.group(1)) if mod_m else 0
                    prof = "[x]" in cols[3].lower() or "x" in cols[3].lower()
                    exp = "[x]" in cols[4].lower() or "x" in cols[4].lower()
                    result[name] = (mod, prof, exp)
                except (ValueError, AttributeError):
                    pass
    return result


def parse_attacks(content: str) -> list[tuple[str, str, str, str, str]]:
    """Return list of (name, attack_bonus, damage, damage_type, notes)."""
    attacks = []
    in_section = False
    header_seen = False
    for line in content.splitlines():
        if re.match(r"^##\s+Attacks", line, re.IGNORECASE):
            in_section = True
            header_seen = False
            continue
        if in_section:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if not header_seen:
                # First pipe row is the header
                header_seen = True
                continue
            if all(re.match(r"^[-: ]+$", c) for c in cols if c):
                continue
            if len(cols) < 4 or not cols[0] or cols[0].startswith("["):
                continue
            name = cols[0]
            atk = cols[1] if len(cols) > 1 else ""
            dmg = cols[2] if len(cols) > 2 else ""
            dtype = cols[3] if len(cols) > 3 else ""
            notes = cols[4] if len(cols) > 4 else ""
            attacks.append((name, atk, dmg, dtype, notes))
    return attacks


def parse_spellcasting(content: str) -> dict:
    """Parse spellcasting section. Returns dict or empty dict if no spellcasting."""
    result: dict = {}
    in_section = False
    header_seen = False
    for line in content.splitlines():
        if re.match(r"^##\s+Spellcasting", line, re.IGNORECASE):
            # Check it's not the template removal note
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            stripped = line.strip()
            # Look for > Remove this section notice (template)
            if stripped.startswith("> Remove"):
                continue
            # Parse the spellcasting info table
            m = re.match(r"\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+?)\s*\|", stripped)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                if key == "Spellcasting Ability":
                    result["ability"] = val
                elif key == "Spell Save DC":
                    try:
                        result["save_dc"] = int(re.search(r"\d+", val).group())
                    except (AttributeError, ValueError):
                        result["save_dc"] = val
                elif key == "Spell Attack Bonus":
                    result["attack_bonus"] = val

    # Spell slots
    slots: list[tuple[str, int, int]] = []
    in_spell_table = False
    for line in content.splitlines():
        if "### Spell Slots" in line:
            in_spell_table = True
            continue
        if in_spell_table:
            stripped = line.strip()
            if not stripped:
                if slots:
                    break
                continue
            if not stripped.startswith("|"):
                break
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) < 3:
                continue
            if cols[0].startswith("[") or all(re.match(r"^[-: ]+$", c) for c in cols if c):
                continue
            try:
                slots.append((cols[0], int(cols[1]), int(cols[2])))
            except (ValueError, IndexError):
                continue
    if slots:
        result["slots"] = slots

    # Cantrips
    cantrips: list[str] = []
    in_cantrips = False
    for line in content.splitlines():
        if re.match(r"^###\s+Cantrips", line, re.IGNORECASE):
            in_cantrips = True
            continue
        if in_cantrips:
            if line.startswith("#"):
                break
            m = re.match(r"^-\s+(.+)", line.strip())
            if m:
                val = m.group(1).strip()
                if not val.startswith("["):
                    cantrips.append(val)
    if cantrips:
        result["cantrips"] = cantrips

    # Known/Prepared Spells — group by level
    spells_by_level: dict[str, list[str]] = {}
    in_spells = False
    header_seen2 = False
    for line in content.splitlines():
        if re.match(r"^###\s+Known\s*/\s*Prepared Spells", line, re.IGNORECASE) or \
           re.match(r"^###\s+Spells", line, re.IGNORECASE):
            in_spells = True
            header_seen2 = False
            continue
        if in_spells:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if not stripped.startswith("|"):
                if stripped.startswith("#"):
                    break
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if not header_seen2:
                header_seen2 = True
                continue
            if all(re.match(r"^[-: ]+$", c) for c in cols if c):
                continue
            if len(cols) < 2 or not cols[0] or cols[0].startswith("["):
                continue
            level = cols[0]
            spell_name = cols[1] if len(cols) > 1 else ""
            if spell_name and not spell_name.startswith("["):
                spells_by_level.setdefault(level, []).append(spell_name)
    if spells_by_level:
        result["spells_by_level"] = spells_by_level

    return result


def parse_features(content: str) -> list[tuple[str, int, int]]:
    """Return list of (name, current_uses, max_uses) for tracked features."""
    feat_pattern = re.compile(
        r"\*\*([^*(]+?)\s*\((\d+)\s*/\s*(\d+)(?:\s*uses?)?\):?\*\*",
        re.IGNORECASE,
    )
    features = []
    for m in feat_pattern.finditer(content):
        features.append((m.group(1).strip(), int(m.group(2)), int(m.group(3))))
    return features


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


def parse_inventory(content: str) -> dict:
    """Parse equipment (worn/wielded + backpack) and gold."""
    result: dict = {}

    # Gold
    gp_m = re.search(r"\|\s*Gold\s*\(gp\)\s*\|\s*(\d+)\s*\|", content, re.IGNORECASE)
    result["gold"] = int(gp_m.group(1)) if gp_m else 0

    # Worn/Wielded
    worn: list[str] = []
    in_worn = False
    for line in content.splitlines():
        if re.match(r"###\s+Worn\s*/\s*Wielded", line, re.IGNORECASE):
            in_worn = True
            continue
        if in_worn:
            if line.startswith("#"):
                break
            m = re.match(r"^-\s+(.+)", line.strip())
            if m:
                val = m.group(1).strip()
                if not val.startswith("["):
                    worn.append(val)
    result["worn"] = worn

    # Backpack items
    backpack: list[str] = []
    in_backpack = False
    header_seen = False
    for line in content.splitlines():
        if re.match(r"###\s+Backpack", line, re.IGNORECASE):
            in_backpack = True
            header_seen = False
            continue
        if in_backpack:
            if line.startswith("##"):
                break
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if not header_seen:
                header_seen = True
                continue
            if all(re.match(r"^[-: ]+$", c) for c in cols if c):
                continue
            if len(cols) >= 2 and cols[0] and not cols[0].startswith("["):
                item = cols[0]
                qty = cols[1] if len(cols) > 1 else ""
                if qty and qty not in ("-", ""):
                    backpack.append(f"{item} ({qty})")
                else:
                    backpack.append(item)
    result["backpack"] = backpack

    return result


def parse_death_saves(content: str) -> tuple[int, int]:
    pattern = re.compile(
        r"\|\s*\*\*Death Saves\*\*\s*\|\s*Successes:\s*(\d+)\s*/\s*Failures:\s*(\d+)\s*\|",
        re.IGNORECASE,
    )
    m = pattern.search(content)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


# ── render helpers ────────────────────────────────────────────────────────────

def render_death_saves(successes: int, failures: int) -> str:
    """Render death saves as ●●○ / ○○○."""
    succ_str = "●" * successes + "○" * (3 - successes)
    fail_str = "●" * failures + "○" * (3 - failures)
    return f"{succ_str} / {fail_str}"


def modifier_str(mod: int) -> str:
    return f"+{mod}" if mod >= 0 else str(mod)


# ── renderer ──────────────────────────────────────────────────────────────────

def render_character(char: dict) -> str:
    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(box_top())

    info = char["info"]
    name = char["name"]
    race = info.get("Race", "?")
    cls = info.get("Class", "?")
    level = info.get("Level", "?")
    player = info.get("Player", "?")
    subclass = info.get("Subclass", "").strip()

    header_title = f"{name.upper()} — {race} {cls} {level}"
    if subclass and not subclass.startswith("["):
        header_title = f"{name.upper()} — {race} {cls} ({subclass}) {level}"
    lines.append(box_row(header_title))
    lines.append(box_row(f"Player: {player}"))

    # ── Combat ────────────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(box_row("COMBAT"))

    hp_cur = char["hp_current"]
    hp_max = char["hp_max"]
    temp_hp = char["temp_hp"]
    ac = char["ac"]
    speed = char["speed"]
    init = char["initiative"]
    hd_str = char["hit_dice"]
    ds_succ, ds_fail = char["death_saves"]

    lines.append(box_row(
        f"HP: {hp_cur}/{hp_max} (Temp: {temp_hp})   AC: {ac}   Speed: {speed}"
    ))
    lines.append(box_row(
        f"Initiative: {modifier_str(init)}   Hit Dice: {hd_str}"
    ))
    lines.append(box_row(
        f"Death Saves: {render_death_saves(ds_succ, ds_fail)}"
    ))

    # ── Ability Scores ────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(box_row("ABILITY SCORES"))

    abilities = char["abilities"]  # dict: name -> (score, mod)
    scores_row = "  ".join(f"{short:>3}" for short in ABILITY_SHORT)
    lines.append(box_row(f"  {scores_row}"))
    vals = []
    mods = []
    for aname in ABILITY_NAMES:
        score, mod = abilities.get(aname, (10, 0))
        vals.append(f"{score:>3}")
        mods.append(f"({modifier_str(mod):>2})")
    lines.append(box_row("  " + "  ".join(vals)))
    lines.append(box_row("  " + "  ".join(mods)))

    # ── Saving Throws ─────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(box_row("SAVING THROWS (proficient marked with *)"))

    saves = char["saving_throws"]
    save_parts = []
    for aname, short in zip(ABILITY_NAMES, ABILITY_SHORT):
        mod, prof = saves.get(aname, (0, False))
        marker = "*" if prof else " "
        save_parts.append(f"{short} {modifier_str(mod)}{marker}")
    # Two rows to fit
    mid = len(save_parts) // 2
    lines.append(box_row("  ".join(save_parts[:mid])))
    lines.append(box_row("  ".join(save_parts[mid:])))

    # ── Skills ────────────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(box_row("SKILLS (proficient *)"))

    skills = char["skills"]
    abilities_data = char["abilities"]

    # Always include Perception for passive; show proficient/expertise skills + Perception
    skill_rows: list[str] = []
    for skill_name, ability_short in SKILL_TABLE:
        entry = skills.get(skill_name)
        if skill_name == "Perception":
            if entry:
                mod, prof, exp = entry
            else:
                # Calculate from WIS modifier
                _, wis_mod = abilities_data.get("Wisdom", (10, 0))
                mod, prof, exp = wis_mod, False, False
            marker = "*" if prof else ""
            if exp:
                marker = "**"
            skill_rows.append(f"Perception {modifier_str(mod)}{marker}")
            continue
        if entry:
            mod, prof, exp = entry
            if prof or exp:
                marker = "**" if exp else "*"
                skill_rows.append(f"{skill_name} {modifier_str(mod)}{marker}")

    # Lay out skill rows — 2 per line
    for i in range(0, len(skill_rows), 2):
        pair = skill_rows[i: i + 2]
        lines.append(box_row("  ".join(f"{p:<24}" for p in pair).rstrip()))

    if not skill_rows:
        lines.append(box_row("None listed"))

    # ── Attacks ───────────────────────────────────────────────────────────────
    attacks = char["attacks"]
    if attacks:
        lines.append(box_mid())
        lines.append(box_row("ATTACKS"))
        for name, atk, dmg, dtype, notes in attacks:
            parts = [f"{name:<16}", f"{atk:<5}", f"{dmg:<10}", f"{dtype:<12}"]
            if notes:
                parts.append(notes)
            lines.append(box_row("  ".join(p for p in parts).rstrip()))

    # ── Spellcasting ──────────────────────────────────────────────────────────
    spell = char["spellcasting"]
    if spell and spell.get("slots"):
        lines.append(box_mid())
        ability = spell.get("ability", "?")
        dc = spell.get("save_dc", "?")
        atk_bonus = spell.get("attack_bonus", "?")
        lines.append(box_row(f"SPELLCASTING ({ability} — DC {dc} — {atk_bonus} to hit)"))

        # Slots
        slot_parts = []
        for level_label, total, remaining in spell["slots"]:
            slot_parts.append(f"{level_label} {remaining}/{total}")
        lines.append(box_row("Slots: " + "  ".join(slot_parts)))

        # Cantrips
        if spell.get("cantrips"):
            lines += wrap_row("Cantrips: " + ", ".join(spell["cantrips"]))

        # Spells by level
        for level_label, spell_list in sorted(
            spell.get("spells_by_level", {}).items(),
            key=lambda kv: kv[0],
        ):
            lines += wrap_row(f"{level_label}: " + ", ".join(spell_list), indent=2)

    # ── Resources ─────────────────────────────────────────────────────────────
    features = char["features"]
    if features:
        lines.append(box_mid())
        lines.append(box_row("RESOURCES"))
        for feat_name, current, max_uses in features:
            lines.append(box_row(f"  {feat_name}: {current}/{max_uses}"))

    # ── Conditions ────────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(box_row("CONDITIONS"))
    conditions = char["conditions"]
    if conditions:
        lines.append(box_row(", ".join(conditions)))
    else:
        lines.append(box_row("None"))

    # ── Inventory ─────────────────────────────────────────────────────────────
    lines.append(box_mid())
    lines.append(box_row("INVENTORY"))
    inv = char["inventory"]
    lines.append(box_row(f"Gold: {inv['gold']} gp"))

    all_items = inv.get("worn", []) + inv.get("backpack", [])
    if all_items:
        lines += wrap_row(", ".join(all_items))
    else:
        lines.append(box_row("Nothing listed"))

    lines.append(box_bot())
    return "\n".join(lines)


# ── parse_character_file ──────────────────────────────────────────────────────

def parse_character_file(filepath: str) -> dict:
    with open(filepath) as f:
        content = f.read()

    name = get_character_name(content, filepath)
    info = parse_info_table(content)
    abilities = parse_ability_scores(content)
    saving_throws = parse_saving_throws(content)
    skills = parse_skills(content)
    attacks = parse_attacks(content)
    spellcasting = parse_spellcasting(content)
    features = parse_features(content)
    conditions = parse_conditions(content)
    inventory = parse_inventory(content)
    ds_succ, ds_fail = parse_death_saves(content)

    hp_max = parse_combat_int(content, "HP Maximum")
    hp_current = parse_combat_int(content, "Current HP") or hp_max
    temp_hp = parse_combat_int(content, "Temporary HP")
    ac = parse_combat_int(content, "Armor Class") or 10
    speed_raw = parse_combat_stat(content, "Speed") or "30 ft"
    init_raw = parse_combat_stat(content, "Initiative Modifier") or "0"
    try:
        init_m = re.search(r"([+-]?\d+)", init_raw)
        initiative = int(init_m.group(1)) if init_m else 0
    except (AttributeError, ValueError):
        initiative = 0

    # Hit dice: "3d10 (remaining: 2)" or similar
    hd_raw = parse_combat_stat(content, "Hit Dice") or "?"
    hit_dice = hd_raw  # Keep as string for display

    return {
        "name": name,
        "info": info,
        "abilities": abilities,
        "saving_throws": saving_throws,
        "skills": skills,
        "attacks": attacks,
        "spellcasting": spellcasting,
        "features": features,
        "conditions": conditions,
        "inventory": inventory,
        "hp_current": hp_current,
        "hp_max": hp_max,
        "temp_hp": temp_hp,
        "ac": ac,
        "speed": speed_raw,
        "initiative": initiative,
        "hit_dice": hit_dice,
        "death_saves": (ds_succ, ds_fail),
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2 or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if args and args[0] in ("-h", "--help") else 1)

    campaign = args[0]
    char_arg = args[1]

    campaign_path = os.path.join(BASE, campaign)
    if not os.path.isdir(campaign_path):
        sys.exit(f"Error: campaign directory not found: {campaign_path}")

    filepath = find_character_file(campaign, char_arg)

    try:
        char = parse_character_file(filepath)
    except Exception as e:
        sys.exit(f"Error: could not parse character file: {e}")

    print(render_character(char))


if __name__ == "__main__":
    main()
