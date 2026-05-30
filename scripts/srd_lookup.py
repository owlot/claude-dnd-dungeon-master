#!/usr/bin/env python3
"""
SRD lookup — returns a single named entry from the D&D 5e SRD.

Usage:
  python3 .claude/scripts/srd_lookup.py monster "Goblin"
  python3 .claude/scripts/srd_lookup.py spell "Fireball"
  python3 .claude/scripts/srd_lookup.py spell-list "Wizard"
  python3 .claude/scripts/srd_lookup.py spell-list "Wizard" "1st Level"
  python3 .claude/scripts/srd_lookup.py condition "Poisoned"
  python3 .claude/scripts/srd_lookup.py item "Bag of Holding"
  python3 .claude/scripts/srd_lookup.py npc "Guard"
  python3 .claude/scripts/srd_lookup.py creature "Riding Horse"
  python3 .claude/scripts/srd_lookup.py class-feature "Rage"
"""

import sys
import json
import re
from pathlib import Path

BASE = Path(__file__).parent.parent.parent / "dnd-5e-srd"
JSON_DIR = BASE / "json"


def load_json(filename):
    path = JSON_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def format_content(content, name):
    """Turn a JSON content list into readable markdown text."""
    lines = [f"#### {name}", ""]
    for item in content:
        if isinstance(item, str):
            lines.append(item)
        elif isinstance(item, list):
            # Nested list = bullet points
            for bullet in item:
                if isinstance(bullet, str):
                    lines.append(f"- {bullet}")
        elif isinstance(item, dict) and "table" in item:
            table = item["table"]
            headers = list(table.keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            rows = zip(*[table[h] for h in headers])
            for row in rows:
                lines.append("| " + " | ".join(str(c) for c in row) + " |")
        lines.append("")
    return "\n".join(lines).strip()


def closest_matches(name, candidates, n=5):
    name_l = name.lower()
    scored = [(c, c.lower().find(name_l)) for c in candidates]
    hits = [(c, s) for c, s in scored if s >= 0]
    hits.sort(key=lambda x: (x[1], len(x[0])))
    if hits:
        return [c for c, _ in hits[:n]]
    # fallback: prefix match
    return [c for c in candidates if c.lower().startswith(name_l[:3])][:n]


def lookup_monster(name):
    data = load_json("11 monsters.json")
    monsters = data["Monsters"]
    name_l = name.lower()
    all_names = []
    for group_key, group in monsters.items():
        if not isinstance(group, dict):
            continue
        for entry_name, entry in group.items():
            if entry_name == "content":
                continue
            all_names.append(entry_name)
            if entry_name.lower() == name_l:
                return format_content(entry["content"], entry_name)
    # Partial match
    for n in all_names:
        if name_l in n.lower():
            group_key_found = None
            for gk, gv in monsters.items():
                if isinstance(gv, dict) and n in gv:
                    group_key_found = gk
                    break
            if group_key_found:
                entry = monsters[group_key_found][n]
                return format_content(entry["content"], n)
    suggestions = closest_matches(name, all_names)
    return f"Not found: {name}\nDid you mean: {', '.join(suggestions) if suggestions else 'no suggestions'}"


def lookup_spell(name):
    data = load_json("08 spellcasting.json")
    spells = data["Spellcasting"]["Spell Descriptions"]
    name_l = name.lower()
    for spell_name, entry in spells.items():
        if spell_name.lower() == name_l:
            return format_content(entry["content"], spell_name)
    # Partial
    for spell_name, entry in spells.items():
        if name_l in spell_name.lower():
            return format_content(entry["content"], spell_name)
    suggestions = closest_matches(name, list(spells.keys()))
    return f"Not found: {name}\nDid you mean: {', '.join(suggestions) if suggestions else 'no suggestions'}"


def lookup_spell_list(class_name, level=None):
    data = load_json("08 spellcasting.json")
    lists = data["Spellcasting"]["Spell Lists"]
    class_l = class_name.lower()
    matched_key = None
    for k in lists:
        if k.lower().startswith(class_l):
            matched_key = k
            break
    if not matched_key:
        return f"No spell list found for: {class_name}\nAvailable: {', '.join(lists.keys())}"
    class_list = lists[matched_key]
    if level:
        level_l = level.lower()
        for lvl_key, spells in class_list.items():
            if lvl_key.lower() == level_l:
                spell_names = spells if isinstance(spells, list) else list(spells)
                return f"### {matched_key} — {lvl_key}\n\n" + "\n".join(f"- {s}" for s in spell_names)
        return f"Level not found: {level}\nAvailable levels: {', '.join(class_list.keys())}"
    lines = [f"### {matched_key}", ""]
    for lvl_key, spells in class_list.items():
        lines.append(f"#### {lvl_key}")
        if isinstance(spells, list):
            for s in spells:
                lines.append(f"- {s}")
        lines.append("")
    return "\n".join(lines).strip()


def lookup_condition(name):
    data = load_json("12 conditions.json")
    top_key = list(data.keys())[0]
    conditions = data[top_key]
    name_l = name.lower()
    for cond_name, entry in conditions.items():
        if cond_name == "content":
            continue
        if cond_name.lower() == name_l:
            if isinstance(entry, dict) and "content" in entry:
                return format_content(entry["content"], cond_name)
            if isinstance(entry, list):
                return format_content(entry, cond_name)
            return f"#### {cond_name}\n\n{entry}"
    suggestions = closest_matches(name, [k for k in conditions if k != "content"])
    return f"Not found: {name}\nDid you mean: {', '.join(suggestions) if suggestions else 'no suggestions'}"


def lookup_item(name):
    data = load_json("10 magic items.json")
    items = data["Magic Items"]
    name_l = name.lower()
    # Exact match (case-insensitive)
    for item_name, entry in items.items():
        if item_name == "content":
            continue
        if item_name.lower() == name_l:
            if isinstance(entry, dict) and "content" in entry:
                return format_content(entry["content"], item_name)
    # Partial match: all query words appear in item name
    query_words = set(name_l.split())
    for item_name, entry in items.items():
        if item_name == "content":
            continue
        item_l = item_name.lower()
        if name_l in item_l or all(w in item_l for w in query_words):
            if isinstance(entry, dict) and "content" in entry:
                return format_content(entry["content"], item_name)
    all_names = [k for k in items if k != "content"]
    suggestions = closest_matches(name, all_names)
    return f"Not found: {name}\nDid you mean: {', '.join(suggestions) if suggestions else 'no suggestions'}"


def lookup_npc(name):
    data = load_json("16 npcs.json")
    top_key = list(data.keys())[0]
    npcs = data[top_key]
    name_l = name.lower()
    for npc_name, entry in npcs.items():
        if npc_name in ("content", "Customizing NPCs"):
            continue
        if npc_name.lower() == name_l:
            if isinstance(entry, dict) and "content" in entry:
                return format_content(entry["content"], npc_name)
    # Partial
    for npc_name, entry in npcs.items():
        if npc_name in ("content", "Customizing NPCs"):
            continue
        if name_l in npc_name.lower():
            if isinstance(entry, dict) and "content" in entry:
                return format_content(entry["content"], npc_name)
    all_names = [k for k in npcs if k not in ("content", "Customizing NPCs")]
    suggestions = closest_matches(name, all_names)
    return f"Not found: {name}\nDid you mean: {', '.join(suggestions) if suggestions else 'no suggestions'}"


def lookup_creature(name):
    data = load_json("15 creatures.json")
    top_key = list(data.keys())[0]
    creatures = data[top_key]
    name_l = name.lower()
    for cname, entry in creatures.items():
        if cname == "content":
            continue
        if cname.lower() == name_l:
            if isinstance(entry, dict) and "content" in entry:
                return format_content(entry["content"], cname)
    # Partial
    for cname, entry in creatures.items():
        if cname == "content":
            continue
        if name_l in cname.lower():
            if isinstance(entry, dict) and "content" in entry:
                return format_content(entry["content"], cname)
    all_names = [k for k in creatures if k != "content"]
    suggestions = closest_matches(name, all_names)
    return f"Not found: {name}\nDid you mean: {', '.join(suggestions) if suggestions else 'no suggestions'}"


def lookup_class_feature(name):
    data = load_json("02 classes.json")
    name_l = name.lower()
    all_feat_names = []
    # Search across all classes' Class Features sections
    for cls_name, cls_data in data.items():
        if not isinstance(cls_data, dict):
            continue
        features = cls_data.get("Class Features", {})
        if not isinstance(features, dict):
            continue
        for feat_name, entry in features.items():
            if feat_name == "content":
                continue
            all_feat_names.append(feat_name)
            if feat_name.lower() == name_l:
                if isinstance(entry, dict) and "content" in entry:
                    return format_content(entry["content"], feat_name)
    # Partial match across all classes
    for cls_name, cls_data in data.items():
        if not isinstance(cls_data, dict):
            continue
        features = cls_data.get("Class Features", {})
        if not isinstance(features, dict):
            continue
        for feat_name, entry in features.items():
            if feat_name == "content":
                continue
            if name_l in feat_name.lower():
                if isinstance(entry, dict) and "content" in entry:
                    return format_content(entry["content"], feat_name)
    # Fallback: markdown regex (catches bold-text features like Sneak Attack)
    return _lookup_class_feature_markdown(name, all_feat_names)


def _lookup_class_feature_markdown(name, known_names):
    md_path = BASE / "markdown" / "02 classes.md"
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    name_l = name.lower()
    # Try bold-text feature headers: **Feature Name**\n\nParagraph...
    pattern = rf'\*\*({re.escape(name)})\*\*\n\n(.*?)(?=\n\*\*[A-Z]|\n###|\Z)'
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if m:
        feat_name = m.group(1)
        body = m.group(2).strip()
        return f"#### {feat_name}\n\n{body}"
    # Try heading-based (### / ####)
    for prefix in ["### ", "#### "]:
        pattern = rf'({re.escape(prefix)}{re.escape(name)}\n.*?)(?=\n### |\n#### |\Z)'
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    suggestions = closest_matches(name, known_names)
    return f"Not found: {name}\nDid you mean: {', '.join(suggestions) if suggestions else 'no suggestions'}"


SOURCE_LABELS = {
    "monster": "monsters",
    "spell": "spells",
    "spell-list": "spell lists",
    "condition": "conditions",
    "item": "magic items",
    "npc": "npcs",
    "creature": "creatures",
    "class-feature": "classes",
}

LOOKUP_FN = {
    "monster": lookup_monster,
    "spell": lookup_spell,
    "condition": lookup_condition,
    "item": lookup_item,
    "npc": lookup_npc,
    "creature": lookup_creature,
    "class-feature": lookup_class_feature,
}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    lookup_type = sys.argv[1].lower()
    name = sys.argv[2]

    if lookup_type == "spell-list":
        level = sys.argv[3] if len(sys.argv) > 3 else None
        result = lookup_spell_list(name, level)
        label = "spell lists"
    elif lookup_type in LOOKUP_FN:
        result = LOOKUP_FN[lookup_type](name)
        label = SOURCE_LABELS[lookup_type]
    else:
        print(f"Unknown type: {lookup_type}")
        print(f"Valid types: {', '.join(LOOKUP_FN.keys())}, spell-list")
        sys.exit(1)

    title = f"{name}" if lookup_type != "spell-list" else f"{name} Spells" + (f" — {sys.argv[3]}" if len(sys.argv) > 3 else "")
    print(f"[SRD: {label}] {title}")
    print("─" * (len(label) + len(title) + 9))
    print(result)


if __name__ == "__main__":
    main()
