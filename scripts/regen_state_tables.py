#!/usr/bin/env python3
"""
Rebuild the `## Objects` and `## Locations` tables in a campaign's state.md from
the ledgers (party/objects/*.md, party/locations/*.md).

    python .claude/scripts/regen_state_tables.py <campaign>

Existing rows keep their position and display name; their party-view columns,
Actual columns and Last changed are refreshed from the ledger's last row (Last
changed ignores rows labelled like "15 (DM correction)"). Ledgers without a row
get one appended at the end of the table. Only the two tables are touched.
"""

import glob
import os
import re
import sys


def ledger(path):
    text = open(path, encoding="utf-8").read()
    title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    rows = [[c.strip() for c in l.strip().strip("|").split("|")]
            for l in text.split("\n") if re.match(r"\| \d", l)]
    numeric = [r for r in rows if re.fullmatch(r"\d+", r[0])]
    return title, rows[-1], (numeric[-1][0] if numeric else re.match(r"\d+", rows[-1][0]).group(0))


def split_actual(cell):
    if cell.strip().lower() == "same":
        return "same", "same"
    m = re.match(r"state:\s*(.*?);\s*detail:\s*(.*)$", cell, re.S)
    return (m.group(1), m.group(2)) if m else ("see ledger", cell)


def object_row(name, last, changed, slug):
    # last = [Session, date, Event, Holder, Location, Status, Actual, Source]
    return f"| {name} | {last[3]} | {last[4]} | {last[5]} | {last[6]} | Session {changed} | party/objects/{slug}.md |"


def location_row(name, last, changed, slug):
    # last = [Session, date, Event, State, Detail, Actual, Source]
    st, dt = split_actual(last[5])
    return f"| {name} | {last[3]} | {last[4]} | {st} | {dt} | Session {changed} | party/locations/{slug}.md |"


def rebuild(lines, heading, kind, make_row, base):
    start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    section = lines[start:end]
    seen = set()
    for i, l in enumerate(section):
        m = re.search(rf"\| party/{kind}/([\w-]+)\.md \|\s*$", l)
        if m and l.startswith("| "):
            slug = m.group(1)
            path = os.path.join(base, kind, slug + ".md")
            if not os.path.exists(path):
                continue
            title, last, changed = ledger(path)
            name = l.strip().strip("|").split("|")[0].strip()
            section[i] = make_row(name, last, changed, slug)
            seen.add(slug)
    add = []
    for path in sorted(glob.glob(os.path.join(base, kind, "*.md"))):
        slug = os.path.splitext(os.path.basename(path))[0]
        if slug not in seen:
            title, last, changed = ledger(path)
            add.append(make_row(title, last, changed, slug))
    # insert new rows after the last table row
    last_row = max(i for i, l in enumerate(section) if l.startswith("|"))
    section[last_row + 1:last_row + 1] = add
    lines[start:end] = section
    return len(seen), len(add)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    base = os.path.join("campaigns", sys.argv[1], "party")
    state = os.path.join(base, "state.md")
    lines = open(state, encoding="utf-8").read().split("\n")
    o = rebuild(lines, "## Objects", "objects", object_row, base)
    l = rebuild(lines, "## Locations", "locations", location_row, base)
    open(state, "w", encoding="utf-8").write("\n".join(lines))
    print(f"Objects: {o[0]} refreshed, {o[1]} added. Locations: {l[0]} refreshed, {l[1]} added.")


if __name__ == "__main__":
    main()
