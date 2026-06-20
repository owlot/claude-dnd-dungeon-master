#!/usr/bin/env python3
"""
Update world.json for a campaign.

All card data lives in website/<campaign>/world.json.
world.html is a static shell — it never needs editing.

Usage:
    python .claude/scripts/update_world.py <campaign> <operation> [args...]

Operations:

  list_cards
      Print all card IDs and display names.

  npc_add <section-id> <card-id> <name> <meta> <tag-class> <description>
      Add a new card to the given section.
      tag-class: tag-ally | tag-enemy | tag-neutral | tag-unknown | tag-dead

  location_add <card-id> <name> <meta> <tag-class> <description>
      Shorthand for npc_add section-places.

  object_add <card-id> <name> <meta> <tag-class> <description>
      Shorthand for npc_add section-objects.

  card_set_desc <card-id> <paragraph-index> <new-text>
      Replace a paragraph by index (0-based).

  card_add_para <card-id> <new-text>
      Append a paragraph to the card.

  card_set_meta <card-id> <new-meta-text>
      Replace the card meta line.

  card_set_tag <card-id> <tag-class>
      Replace all tags with a single tag.

  card_add_tag <card-id> <tag-class>
      Add a tag if not already present.

  card_remove_tag <card-id> <tag-class>
      Remove a specific tag.

  card_set_portrait <card-id> <image-path>
      Set or replace the portrait image path.

  card_set_place <card-id> <image-path>
      Set or replace the place image path.

  replace <card-id> <old-text> <new-text>
      Replace first occurrence of old-text in the card's body.

  replace_all <old-text> <new-text>
      Replace all occurrences in every card's body across the whole world.
"""

import sys
import os
import json
import shutil


def load(campaign):
    path = os.path.join("website", campaign, "world.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f), path


def save(world, path):
    bak = path + ".bak"
    shutil.copy(path, bak)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(world, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find_card(world, card_id):
    for section in world["sections"]:
        for card in section["cards"]:
            if card["id"] == card_id:
                return card
    return None


def find_section(world, section_id):
    for section in world["sections"]:
        if section["id"] == section_id:
            return section
    return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    campaign = sys.argv[1]
    op = sys.argv[2]
    args = sys.argv[3:]

    if op == "list_cards":
        world, _ = load(campaign)
        for section in world["sections"]:
            print(f"\n[{section['id']}] {section['title']}")
            for card in section["cards"]:
                print(f"  {card['id']:40s} {card['name']}")
        return

    world, path = load(campaign)

    # ── Card creation ──────────────────────────────────────────────────────────

    if op in ("npc_add", "location_add", "object_add"):
        if op == "location_add":
            args = ["section-places"] + args
        elif op == "object_add":
            args = ["section-objects"] + args

        if len(args) < 6:
            print(f"Usage: {op} <section-id> <card-id> <name> <meta> <tag-class> <description>")
            sys.exit(1)

        section_id, card_id, name, meta, tag_class, description = args[:6]
        section = find_section(world, section_id)
        if not section:
            print(f"Error: section '{section_id}' not found")
            sys.exit(1)

        if find_card(world, card_id):
            print(f"Error: card '{card_id}' already exists")
            sys.exit(1)

        card = {
            "id": card_id,
            "name": name,
            "meta": meta,
            "tags": [tag_class] if tag_class else [],
            "body": [description],
        }
        section["cards"].append(card)
        save(world, path)
        print(f"Added card '{card_id}' to {section_id}")
        return

    # ── Card mutations ─────────────────────────────────────────────────────────

    if op == "card_set_desc":
        card_id, idx, text = args[0], int(args[1]), args[2]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        while len(card["body"]) <= idx:
            card["body"].append("")
        card["body"][idx] = text
        save(world, path)
        print(f"Updated {card_id} paragraph {idx}")
        return

    if op == "card_add_para":
        card_id, text = args[0], args[1]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        card["body"].append(text)
        save(world, path)
        print(f"Appended paragraph to {card_id}")
        return

    if op == "card_set_meta":
        card_id, meta = args[0], args[1]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        card["meta"] = meta
        save(world, path)
        print(f"Updated meta for {card_id}")
        return

    if op == "card_set_tag":
        card_id, tag = args[0], args[1]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        card["tags"] = [tag]
        save(world, path)
        print(f"Set tag for {card_id}: {tag}")
        return

    if op == "card_add_tag":
        card_id, tag = args[0], args[1]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        if tag not in card["tags"]:
            card["tags"].append(tag)
            save(world, path)
            print(f"Added tag {tag} to {card_id}")
        else:
            print(f"Tag {tag} already present on {card_id}")
        return

    if op == "card_remove_tag":
        card_id, tag = args[0], args[1]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        if tag in card["tags"]:
            card["tags"].remove(tag)
            save(world, path)
            print(f"Removed tag {tag} from {card_id}")
        else:
            print(f"Tag {tag} not found on {card_id}")
        return

    if op == "card_set_field":
        card_id, field, value = args[0], args[1], args[2]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        card[field] = value
        save(world, path)
        print(f"Set {field} for {card_id}: {value}")
        return

    if op == "card_set_portrait":
        card_id, img = args[0], args[1]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        card["portrait"] = img
        save(world, path)
        print(f"Set portrait for {card_id}: {img}")
        return

    if op == "card_set_place":
        card_id, img = args[0], args[1]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        card["place"] = img
        save(world, path)
        print(f"Set place image for {card_id}: {img}")
        return

    if op == "replace":
        card_id, old, new = args[0], args[1], args[2]
        card = find_card(world, card_id)
        if not card: print(f"Card not found: {card_id}"); sys.exit(1)
        replaced = False
        for i, para in enumerate(card["body"]):
            if old in para:
                card["body"][i] = para.replace(old, new, 1)
                replaced = True
                break
        if replaced:
            save(world, path)
            print(f"Replaced in {card_id}")
        else:
            print(f"Text not found in {card_id}: {old!r}")
        return

    if op == "replace_all":
        old, new = args[0], args[1]
        count = 0
        for section in world["sections"]:
            for card in section["cards"]:
                for i, para in enumerate(card["body"]):
                    if old in para:
                        card["body"][i] = para.replace(old, new)
                        count += 1
        if count:
            save(world, path)
            print(f"Replaced {count} occurrences")
        else:
            print(f"No occurrences found: {old!r}")
        return

    print(f"Unknown operation: {op}")
    sys.exit(1)


if __name__ == "__main__":
    main()
