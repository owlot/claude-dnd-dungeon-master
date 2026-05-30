#!/usr/bin/env python3
"""
combat_status.py — D&D 5e combat tracker for Claude DM assistant.

Usage:
  python scripts/combat_status.py <campaign> <encounter>
      Display current combat status (reads combat_state.json).

  python scripts/combat_status.py <campaign> --init <encounter_name>
      Initialize combat_state.json from an encounter markdown file.
      Prompts for player initiative rolls interactively.

  python scripts/combat_status.py <campaign> --update '<json_patch>'
      Apply a JSON patch to combat_state.json and display updated status.

Patch keys:
  {"name": "...", "hp_current": N}         — update a combatant's HP
  {"name": "...", "conditions": [...]}     — set conditions list
  {"name": "...", "death_saves": {...}}    — set death save counts
  {"advance_turn": true}                   — move to next living combatant
  {"round": N}                             — set the round number
"""

import json
import os
import random
import re
import sys

# ── path helpers ──────────────────────────────────────────────────────────────

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "campaigns")


def campaign_dir(campaign: str) -> str:
    return os.path.join(BASE, campaign)


def state_path(campaign: str) -> str:
    return os.path.join(campaign_dir(campaign), "combat_state.json")


def encounter_path(campaign: str, encounter: str) -> str:
    return os.path.join(campaign_dir(campaign), "encounters", f"{encounter}.md")


# ── markdown table parser ─────────────────────────────────────────────────────

def parse_md_table(lines: list[str], start_keyword: str) -> list[dict]:
    """
    Find the first markdown table after a line containing start_keyword.
    Returns a list of dicts keyed by column header (stripped, lowercased).
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
                break   # blank line after rows — table is done
            continue
        if not stripped.startswith("|"):
            if rows or header:
                break
            continue
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if not header:
            header = [c.strip("* ").lower() for c in cols]
            continue
        # separator row
        if all(re.match(r"^[-: ]+$", c) for c in cols if c):
            continue
        if len(cols) < len(header):
            cols += [""] * (len(header) - len(cols))
        rows.append({header[i]: cols[i] for i in range(len(header))})
    return rows


# ── encounter file parser ─────────────────────────────────────────────────────

def parse_encounter(filepath: str) -> list[dict]:
    """
    Parse an encounter markdown file and return a list of enemy combatant dicts:
      name, count, hp_max, ac, initiative_mod
    """
    with open(filepath) as f:
        lines = f.readlines()

    rows = parse_md_table(lines, "## Enemies")
    enemies: list[dict] = []
    for row in rows:
        name = row.get("name", "").strip()
        if not name or name.startswith("["):
            continue
        try:
            count = int(row.get("count", "1") or "1")
        except ValueError:
            count = 1
        try:
            hp_max = int(re.sub(r"[^\d]", "", row.get("hp each", "8") or "8") or "8")
        except ValueError:
            hp_max = 8
        try:
            ac = int(re.sub(r"[^\d]", "", row.get("ac", "10") or "10") or "10")
        except ValueError:
            ac = 10
        # initiative column may be "+3", "3", "-1", etc.
        init_raw = re.sub(r"[^\d\-+]", "", row.get("initiative", "0") or "0")
        try:
            init_mod = int(init_raw)
        except ValueError:
            init_mod = 0
        enemies.append({
            "name": name,
            "count": count,
            "hp_max": hp_max,
            "ac": ac,
            "initiative_mod": init_mod,
        })
    return enemies


# ── display rendering ─────────────────────────────────────────────────────────

WIDTH = 60   # inner content width (between ║ and ║)


def pad(text: str, width: int) -> str:
    """Left-pad text to exactly width chars, truncating if needed."""
    if len(text) > width:
        text = text[: width - 1] + "…"
    return text.ljust(width)


def render_combat(state: dict) -> str:
    combatants: list[dict] = state["combatants"]
    round_num: int = state.get("round", 1)
    active_idx: int = state.get("active_index", 0)

    # Sort: living first (by initiative desc), dead last
    living = [c for c in combatants if c["hp_current"] > 0]
    dead = [c for c in combatants if c["hp_current"] <= 0]
    living_sorted = sorted(living, key=lambda c: -c["initiative"])
    dead_sorted = sorted(dead, key=lambda c: -c["initiative"])
    ordered = living_sorted + dead_sorted

    # Determine which combatant is active by matching state active_index against
    # the original list ordering.
    active_name = None
    if 0 <= active_idx < len(combatants):
        active_name = combatants[active_idx]["name"]

    border_top = "╔" + "═" * (WIDTH + 2) + "╗"
    border_mid = "╠" + "═" * (WIDTH + 2) + "╣"
    border_bot = "╚" + "═" * (WIDTH + 2) + "╝"
    sep_inner  = "║  " + "─" * WIDTH + "  ║"

    def row(content: str) -> str:
        return "║  " + pad(content, WIDTH) + "  ║"

    lines = [border_top]
    lines.append(row(f"COMBAT — Round {round_num}"))
    lines.append(border_mid)
    lines.append(row("INITIATIVE  NAME              HP        AC  STATUS"))
    lines.append(sep_inner)

    for c in ordered:
        active_marker = "►" if c["name"] == active_name else " "
        init_tag = f"[{c['initiative']}]".ljust(4)
        ctype = "PC" if c["type"] == "pc" else "Enemy"
        name_field = f"{c['name']} ({ctype})"

        hp_c = c["hp_current"]
        hp_m = c["hp_max"]
        hp_str = f"{hp_c}/{hp_m}"

        ac_str = str(c["ac"])

        # Status
        conditions = c.get("conditions", [])
        death = c.get("death_saves", {"successes": 0, "failures": 0})
        if hp_c <= 0:
            if c["type"] == "pc":
                s = death.get("successes", 0)
                f = death.get("failures", 0)
                status = f"UNCONSCIOUS ({s}S/{f}F)"
            else:
                status = "DEAD"
        elif conditions:
            status = ", ".join(conditions)
        else:
            status = "—"

        # Fixed column layout: marker(1) space(1) init(5) space(1) name(18) space(1) hp(9) space(1) ac(3) space(1) status
        line = (
            f"{active_marker} {init_tag:<5} {name_field:<18} {hp_str:<9} {ac_str:<3} {status}"
        )
        lines.append(row(line))

    lines.append(border_bot)
    return "\n".join(lines)


# ── state I/O ─────────────────────────────────────────────────────────────────

def load_state(campaign: str) -> dict:
    path = state_path(campaign)
    if not os.path.exists(path):
        sys.exit(f"Error: combat_state.json not found at {path}\n"
                 f"Run with --init <encounter> to start a new combat.")
    with open(path) as f:
        return json.load(f)


def save_state(campaign: str, state: dict) -> None:
    path = state_path(campaign)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


# ── --init ────────────────────────────────────────────────────────────────────

def cmd_init(campaign: str, encounter: str) -> None:
    enc_path = encounter_path(campaign, encounter)
    if not os.path.exists(enc_path):
        sys.exit(f"Error: encounter file not found: {enc_path}")

    enemies = parse_encounter(enc_path)
    if not enemies:
        sys.exit("Error: no enemies found in encounter file. "
                 "Check the ## Enemies table format.")

    combatants: list[dict] = []

    # Expand enemies by count
    for enemy in enemies:
        count = enemy["count"]
        for i in range(count):
            if count == 1:
                label = enemy["name"]
            else:
                # Use A/B/C suffixes only if name doesn't already end in one
                # to avoid "Goblin A A" for a pre-lettered name.
                suffix = chr(65 + i)  # A, B, C, …
                base = enemy["name"].rstrip()
                if len(base) > 1 and base[-1].isalpha() and base[-2] in (" ", "("):
                    # Name already ends with a distinguishing letter — use number
                    label = f"{base}{i + 1}"
                else:
                    label = f"{base} {suffix}"
            roll = random.randint(1, 20) + enemy["initiative_mod"]
            combatants.append({
                "name": label,
                "type": "enemy",
                "initiative": roll,
                "hp_current": enemy["hp_max"],
                "hp_max": enemy["hp_max"],
                "ac": enemy["ac"],
                "conditions": [],
                "death_saves": {"successes": 0, "failures": 0},
            })

    # Read party from character files
    char_dir = os.path.join(campaign_dir(campaign), "characters")
    pc_names: list[dict] = []
    if os.path.isdir(char_dir):
        for fname in sorted(os.listdir(char_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(char_dir, fname)
            with open(fpath) as f:
                content = f.read()
            # Extract character name from first heading
            char_name_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            char_name = char_name_match.group(1).strip() if char_name_match else fname[:-3]

            # Extract combat stats table
            # Rows look like: | **Label** | 42 |
            hp_max = 0
            hp_current = 0
            ac = 10
            stat_pattern = re.compile(r"\|\s*(\d+)\s*\|?\s*$")
            for line in content.splitlines():
                if "**HP Maximum**" in line:
                    m = stat_pattern.search(line)
                    if m:
                        hp_max = int(m.group(1))
                if "**Current HP**" in line:
                    m = stat_pattern.search(line)
                    if m:
                        hp_current = int(m.group(1))
                if "**Armor Class**" in line:
                    m = stat_pattern.search(line)
                    if m:
                        ac = int(m.group(1))

            pc_names.append({"name": char_name, "hp_max": hp_max or 10,
                             "hp_current": hp_current or hp_max or 10, "ac": ac})

    print("\n=== INITIATIVE ROLLS ===")
    print("Enter each player's d20 roll and their modifier when prompted.")
    print("Format: <roll> <modifier>  (e.g. '14 2' for a 14 + 2 = 16)\n")

    for pc in pc_names:
        while True:
            try:
                raw = input(f"  {pc['name']} — roll d20 + modifier: ").strip()
                parts = raw.split()
                if len(parts) == 1:
                    total = int(parts[0])
                elif len(parts) == 2:
                    total = int(parts[0]) + int(parts[1])
                else:
                    raise ValueError
                combatants.append({
                    "name": pc["name"],
                    "type": "pc",
                    "initiative": total,
                    "hp_current": pc["hp_current"],
                    "hp_max": pc["hp_max"],
                    "ac": pc["ac"],
                    "conditions": [],
                    "death_saves": {"successes": 0, "failures": 0},
                })
                break
            except (ValueError, EOFError):
                print("  Please enter a number (roll) or two numbers (roll modifier).")

    if not pc_names:
        print("  (No character files found — add PCs manually to combat_state.json)")

    # Sort by initiative descending; active_index = 0
    combatants.sort(key=lambda c: -c["initiative"])

    state = {
        "campaign": campaign,
        "encounter": encounter,
        "round": 1,
        "active_index": 0,
        "combatants": combatants,
    }
    save_state(campaign, state)
    print()
    print(render_combat(state))


# ── --update ──────────────────────────────────────────────────────────────────

def cmd_update(campaign: str, patch_str: str) -> None:
    state = load_state(campaign)
    try:
        patch = json.loads(patch_str)
    except json.JSONDecodeError as e:
        sys.exit(f"Error: invalid JSON patch: {e}")

    combatants: list[dict] = state["combatants"]

    if "advance_turn" in patch and patch["advance_turn"]:
        # Move active_index to next combatant that is not dead (for enemies) /
        # not dead-dead (for PCs, unconscious still gets turns for death saves).
        n = len(combatants)
        if n == 0:
            sys.exit("Error: no combatants in state.")
        start = (state["active_index"] + 1) % n
        for offset in range(n):
            idx = (start + offset) % n
            c = combatants[idx]
            # PCs at 0 HP are UNCONSCIOUS — they still get death save turns
            # Enemy at 0 HP is dead — skip
            if c["type"] == "enemy" and c["hp_current"] <= 0:
                continue
            state["active_index"] = idx
            # Wrap round
            if idx == 0:
                state["round"] = state.get("round", 1) + 1
            break

    elif "round" in patch:
        state["round"] = patch["round"]

    elif "name" in patch:
        target_name = patch["name"]
        found = False
        for c in combatants:
            if c["name"].lower() == target_name.lower():
                if "hp_current" in patch:
                    hp = int(patch["hp_current"])
                    # Clamp to [0, hp_max]
                    c["hp_current"] = max(0, min(hp, c["hp_max"]))
                if "conditions" in patch:
                    c["conditions"] = patch["conditions"]
                if "death_saves" in patch:
                    c["death_saves"] = patch["death_saves"]
                if "ac" in patch:
                    c["ac"] = int(patch["ac"])
                found = True
                break
        if not found:
            sys.exit(f"Error: combatant '{target_name}' not found.")

    else:
        sys.exit("Error: unrecognized patch keys. Valid keys: name, advance_turn, round.")

    save_state(campaign, state)
    print(render_combat(state))


# ── display ───────────────────────────────────────────────────────────────────

def cmd_display(campaign: str) -> None:
    state = load_state(campaign)
    print(render_combat(state))


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    campaign = args[0]

    if not os.path.isdir(campaign_dir(campaign)):
        sys.exit(f"Error: campaign directory not found: {campaign_dir(campaign)}")

    if args[1] == "--init":
        if len(args) < 3:
            sys.exit("Error: --init requires an encounter name.")
        cmd_init(campaign, args[2])

    elif args[1] == "--update":
        if len(args) < 3:
            sys.exit("Error: --update requires a JSON patch string.")
        cmd_update(campaign, args[2])

    else:
        # Positional: <campaign> <encounter> — just display current state
        # (encounter arg is accepted but ignored if state already exists)
        cmd_display(campaign)


if __name__ == "__main__":
    main()
