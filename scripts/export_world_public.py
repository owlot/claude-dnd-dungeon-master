#!/usr/bin/env python3
"""
Export the spoiler-free (party view) data of tracked objects and locations.

The object ledgers (campaigns/<campaign>/party/objects/*.md) and location
ledgers (campaigns/<campaign>/party/locations/*.md) keep two views of every row:
what the party knows ("party view", safe for the website) and the truth
("Actual (DM-only)"). This script reads ONLY the party-view columns, the
Event column and each file's "What it is" line. The Actual columns, the Source
column and the "Campaign file" line are never read into the output, so the
website generator cannot leak them.

Usage:
    python .claude/scripts/export_world_public.py <campaign> [--out FILE] [--through N]

Output: JSON with "places" and "objects" (written to FILE or stdout).

--through N publishes only what the party knew up to Session N (the last
published session page): ledger rows from later sessions are dropped, items
with no row up to N are left out, and an item that has later rows loses its
Description (the card falls back to its one-line "What it is"), because a
Description is rewritten as the party learns more. sync_world_cards.py passes
the highest session in website/<campaign>/sessions.json.

Safety (structural first: the Actual and Source columns are never read):
  ERROR (exit 1, nothing written)
    - a ledger table does not have exactly the expected header
    - a party-view cell, Event cell or "What it is" line contains a DM marker
      such as "[DM", "DM ruling", "the DM", or out-of-fiction bookkeeping words ("the log", "state.md", "canonical", "info file", "session log")
    - a term listed in campaigns/<campaign>/party/dm-secrets.txt (one term or
      phrase per line, case-insensitive; "#" comments allowed) appears anywhere
      in the public output. Keep this list for the secrets you care about
      (villains' names, hidden locations, true holders).
"""

import argparse
import glob
import json
import os
import re
import sys

OBJECT_HEADER = ["Session", "In-game date", "Event", "Holder (party)",
                 "Location (party)", "Status (party)", "Actual (DM-only)", "Source"]
LOCATION_HEADER = ["Session", "In-game date", "Event", "State (party)",
                   "Detail (party)", "Actual (DM-only)", "Source"]

DM_MARKERS = re.compile(
    r"\[DM|DM-only|DM ruling|DM confirm|DM correction|\bthe DM\b|\bDM said\b"
    r"|state\.md|\bcanonical\b|\binfo file\b|\bsession log\b|\blogs?\b"
    r"|\b[A-Z]{1,2}\d{1,2}[a-z]?\b",  # map room codes (X7, Q11, Z3) and session shorthand (S14)
    re.I,
)
PLACE_TAG = {
    "rumored": "tag-unknown",
    "exact location unknown": "tag-unknown",
    "known on map": "tag-location",
    "visited": "tag-visited",
    "partially explored": "tag-visited",
    "explored": "tag-visited",
    "changed": "tag-visited",
}


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(path, expected):
    text = open(path, encoding="utf-8").read()
    errors = []
    title = re.search(r"^# (.+)$", text, re.M)
    what = re.search(r"^\*\*What it is\*\*:\s*(.+)$", text, re.M)
    desc = re.search(r"^## Description\s*\n(.*?)(?=^## )", text, re.M | re.S)
    description = [para.strip() for para in re.split(r"\n\s*\n", desc.group(1).strip()) if para.strip()] if desc else []
    rows = []
    in_ledger = False
    header_ok = False
    for line in text.split("\n"):
        if line.startswith("## Ledger"):
            in_ledger = True
            continue
        if not in_ledger or not line.startswith("|"):
            continue
        c = cells(line)
        if c[0] == "Session":
            header_ok = c == expected
            if not header_ok:
                errors.append(f"{path}: ledger header is not the expected party/actual layout: {c}")
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        if len(c) != len(expected):
            errors.append(f"{path}: row has {len(c)} cells, expected {len(expected)}: {line[:60]}")
            continue
        rows.append(dict(zip(expected, c)))
    if not header_ok and not errors:
        errors.append(f"{path}: no ledger table found")
    return {
        "slug": os.path.splitext(os.path.basename(path))[0],
        "name": title.group(1).strip() if title else os.path.basename(path),
        "what": what.group(1).strip() if what else "",
        "description": description,
        "rows": rows,
    }, errors


def public_text(rec, party_cols):
    """Text of a record that is allowed to be public (for marker checks)."""
    parts = [rec["name"], rec["slug"], rec["what"]] + rec.get("description", [])
    for r in rec["rows"]:
        parts.append(r["Event"])
        parts.append(r["In-game date"])
        parts.extend(r[c] for c in party_cols)
    return parts


def check(rec, party_cols):
    errors = []
    for part in public_text(rec, party_cols):
        if DM_MARKERS.search(part):
            errors.append(f"{rec['slug']}: DM marker in public text: {part[:80]}")
    return errors


def clean_session(label):
    """"15 (DM confirmation)" -> "15"; the parenthetical is bookkeeping, not public."""
    m = re.match(r"\d+", label.strip())
    return m.group(0) if m else label.strip()


def session_no(label):
    m = re.match(r"\d+", label.strip())
    return int(m.group(0)) if m else 0


def through(rec, n):
    """Drop rows after session n; None if nothing is left."""
    if n is None:
        return rec
    kept = [r for r in rec["rows"] if session_no(r["Session"]) <= n]
    if not kept:
        return None
    out = dict(rec, rows=kept)
    if len(kept) < len(rec["rows"]):
        out["description"] = []  # rewritten after session n: fall back to "What it is"
    return out


def latest(rec):
    """Latest row (current state) and the session of the last real change.

    Rows labelled like "15 (DM correction)" set the current state but do not
    count as a change, so last_changed uses the last purely numeric session."""
    numeric = [r for r in rec["rows"] if re.fullmatch(r"\d+", r["Session"])]
    changed = numeric[-1]["Session"] if numeric else clean_session(rec["rows"][-1]["Session"])
    return rec["rows"][-1], changed


def build_place(rec):
    last, changed = latest(rec)
    state = last["State (party)"].strip()
    if state in ("", "—", "-"):
        return None
    return {
        "id": rec["slug"],
        "name": rec["name"],
        "what": rec["what"],
        "description": rec["description"],
        "state": state,
        "detail": last["Detail (party)"],
        "tag": PLACE_TAG.get(state, "tag-visited"),
        "last_changed_session": changed,
        "history": [
            {"session": clean_session(r["Session"]), "when": r["In-game date"], "event": r["Event"],
             "state": r["State (party)"], "detail": r["Detail (party)"]}
            for r in rec["rows"] if r["State (party)"].strip() not in ("", "—", "-")
        ],
    }


def party_pattern(campaign):
    """'party' plus the first name of every card in world.json's Party section."""
    names = ["party"]
    path = os.path.join("website", campaign, "world.json")
    if os.path.exists(path):
        for sec in json.load(open(path, encoding="utf-8")).get("sections", []):
            if sec["id"] == "section-party":
                for c in sec["cards"]:
                    names += [w for w in re.findall(r"[A-Za-z']+", c["name"].split(" — ")[0])[:1]]
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)


def build_object(rec, party_re):
    last, changed = latest(rec)
    holder = last["Holder (party)"]
    if party_re.search(holder):
        tag = "tag-with-party"
    elif holder.lower().startswith("unknown"):
        tag = "tag-unknown"
    else:
        tag = "tag-handed-off"
    return {
        "id": rec["slug"],
        "name": rec["name"],
        "what": rec["what"],
        "description": rec["description"],
        "holder": holder,
        "location": last["Location (party)"],
        "status": last["Status (party)"],
        "tag": tag,
        "last_changed_session": changed,
        "history": [
            {"session": clean_session(r["Session"]), "when": r["In-game date"], "event": r["Event"],
             "holder": r["Holder (party)"], "location": r["Location (party)"],
             "status": r["Status (party)"]}
            for r in rec["rows"]
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("campaign")
    ap.add_argument("--out")
    ap.add_argument("--through", type=int)
    args = ap.parse_args()

    base = os.path.join("campaigns", args.campaign, "party")
    errors = []
    places, objects = [], []
    records = []  # (kind, rec, party_cols)
    party_re = party_pattern(args.campaign)

    for path in sorted(glob.glob(os.path.join(base, "locations", "*.md"))):
        rec, e = parse(path, LOCATION_HEADER)
        errors += e
        if e:
            continue
        ce = check(rec, ["State (party)", "Detail (party)"])
        errors += ce
        records.append(("place", rec, ["State (party)", "Detail (party)"]))
        rec = through(rec, args.through)
        p = build_place(rec) if rec else None
        if p:
            places.append(p)

    for path in sorted(glob.glob(os.path.join(base, "objects", "*.md"))):
        rec, e = parse(path, OBJECT_HEADER)
        errors += e
        if e:
            continue
        ce = check(rec, ["Holder (party)", "Location (party)", "Status (party)"])
        errors += ce
        records.append(("object", rec, ["Holder (party)", "Location (party)", "Status (party)"]))
        rec = through(rec, args.through)
        if rec:
            objects.append(build_object(rec, party_re))

    secrets_path = os.path.join(base, "dm-secrets.txt")
    if os.path.exists(secrets_path):
        secrets = [l.strip() for l in open(secrets_path, encoding="utf-8")
                   if l.strip() and not l.strip().startswith("#")]
        for _, rec, cols in records:
            public = " ".join(public_text(rec, cols)).lower()
            for t in secrets:
                if t.lower() in public:
                    errors.append(f"{rec['slug']}: secret term '{t}' appears in public text")

    for m in errors:
        print("ERROR:", m, file=sys.stderr)
    if errors:
        sys.exit(1)
    out = json.dumps({"campaign": args.campaign, "places": places, "objects": objects},
                     indent=2, ensure_ascii=False) + "\n"
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Wrote {args.out}: {len(places)} places, {len(objects)} objects", file=sys.stderr)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
