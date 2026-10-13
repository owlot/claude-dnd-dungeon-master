#!/usr/bin/env python3
"""
Publish the party view of tracked objects and locations to the website and
make sure every one of them has a card in world.json.

    python .claude/scripts/sync_world_cards.py <campaign>

What it does:
  1. Runs the spoiler-safe export (see export_world_public.py) and writes
     website/<campaign>/world-public.json. Nothing is written if the export
     reports an ERROR.
  2. Updates website/<campaign>/world.json, sections section-places and
     section-objects:
       - a card that already exists (matched by its "public" field, by its id,
         or by website/<campaign>/world-aliases.json {"old-card-id": "slug"})
         gets "public": "<slug>"; its hand-written body, meta and tags are
         removed (world.js renders them from world-public.json) and its image
         (place / portrait) is kept; the card id is kept so existing
         world.html#anchor links still work
       - a tracked item without a card gets a stub card {id, name, public}
       - cards for things that are not tracked (no public entry) are left
         untouched
  3. Backs up the first-ever world.json to world.json.pre-public.

world.js merges world-public.json into those cards: latest state in the card
and a collapsible History panel.
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    campaign = sys.argv[1]
    site = os.path.join("website", campaign)
    pub_path = os.path.join(site, "world-public.json")
    world_path = os.path.join(site, "world.json")

    r = subprocess.run([sys.executable, os.path.join(HERE, "export_world_public.py"),
                        campaign, "--out", pub_path])
    if r.returncode != 0:
        print("Export failed; world.json not touched.", file=sys.stderr)
        sys.exit(r.returncode)
    pub = json.load(open(pub_path, encoding="utf-8"))

    aliases = {}
    alias_path = os.path.join(site, "world-aliases.json")
    if os.path.exists(alias_path):
        aliases = json.load(open(alias_path, encoding="utf-8"))

    bak = world_path + ".pre-public"
    if not os.path.exists(bak):
        shutil.copy(world_path, bak)
    world = json.load(open(world_path, encoding="utf-8"))

    def section(sid):
        for s in world["sections"]:
            if s["id"] == sid:
                return s
        raise SystemExit(f"world.json has no section {sid}")

    stats = {"converted": 0, "stubs": 0}
    for sid, key in (("section-places", "places"), ("section-objects", "objects")):
        sec = section(sid)
        by_public = {}
        for card in sec["cards"]:
            slug = card.get("public") or aliases.get(card["id"]) or card["id"]
            by_public.setdefault(slug, card)
        for entry in pub[key]:
            slug = entry["id"]
            card = by_public.get(slug)
            if card is None:
                sec["cards"].append({"id": slug, "name": entry["name"], "public": slug})
                stats["stubs"] += 1
                continue
            if card.get("public") != slug or "body" in card:
                stats["converted"] += 1
            card["public"] = slug
            for k in ("body", "meta", "tags"):
                card.pop(k, None)

    with open(world_path, "w", encoding="utf-8") as f:
        json.dump(world, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"world.json: {stats['converted']} cards converted, {stats['stubs']} stub cards added", file=sys.stderr)


if __name__ == "__main__":
    main()
