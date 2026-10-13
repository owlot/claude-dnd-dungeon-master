#!/usr/bin/env python3
"""
List the objects, places, relationships and NPCs linked to one NPC, as
CANDIDATE linked facts for an ACTIVATE / ANSWER message (see
.claude/rules/npc-memory.md, "Linked facts and NEED").

    python .claude/scripts/npc_links.py <campaign> <npc-slug>                    # ledger candidates
    python .claude/scripts/npc_links.py <campaign> <npc-slug> --scene "DM input"   # who this NPC knows of, per tier
    python .claude/scripts/npc_links.py <campaign> <npc-slug> --people a,b         # same, for named people
    python .claude/scripts/npc_links.py <campaign> --audit                         # NPC files without `## who knows`

--scene / --people print, for every other NPC mentioned in the text (or named),
only the tiers of that person's `## who knows` section that apply to THIS NPC:
the bullets tagged [everyone] plus those whose tags overlap the NPC's own
`groups:` line (in `## character`). [secret] bullets are never printed. The
output is paste-ready for the `Linked facts` line of an ACTIVATE / ANSWER
message. Add --with-ledger to also print the ledger candidates, --all to print
every tier.

Reads party/objects/*.md, party/locations/*.md, party/relationships.md and the
other NPCs' memory files, and prints every ledger row / relationship row that
names the NPC (full name, first name or surname). Only the party-view columns
and Event cells are printed; the DM-only Actual columns are never shown.

The output is a candidate list for the main thread: the party view is what the
party knows, not what the NPC knows. Pass the NPC only what it took part in,
was told, or would know as common knowledge, and let the agent NEED the rest.
"""

import glob
import os
import re
import sys


def names_for(base, slug):
    names = set()
    for path in (os.path.join(base, "npc-memory", slug + ".md"),
                 os.path.join("campaigns", os.path.basename(os.path.dirname(base)), "info", "npcs", slug + ".md")):
        if os.path.exists(path):
            text = open(path, encoding="utf-8").read()
            m = re.search(r"^# NPC memory: (.+?) \(", text, re.M) or re.search(r"^name:\s*(.+)$", text, re.M)
            if m:
                names.add(re.sub(r"\s*\(.*?\)", "", m.group(1)).strip())
    if not names:
        names.add(slug.replace("-", " ").title())
    parts = set()
    for n in list(names):
        words = [w for w in re.findall(r"[A-Za-z']+", n) if len(w) >= 4]
        parts.update(words[:1] + words[-1:])
    return sorted(names | parts, key=len, reverse=True)


def pattern(names):
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)


def ledger_rows(path):
    text = open(path, encoding="utf-8").read()
    title = re.search(r"^# (.+)$", text, re.M).group(1).strip()
    what = re.search(r"^\*\*What it is\*\*:\s*(.+)$", text, re.M)
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in text.split("\n") if re.match(r"\| \d", l)]
    return (title + " — " + what.group(1).strip()) if what else title, rows


def clip(s, n=170):
    return s if len(s) <= n else s[: n - 1] + "…"


def npc_path(campaign, slug):
    return os.path.join("campaigns", campaign, "info", "npcs", slug + ".md")


def npc_groups(campaign, slug):
    path = npc_path(campaign, slug)
    if not os.path.exists(path):
        return None
    m = re.search(r"^groups:\s*(.+)$", open(path, encoding="utf-8").read(), re.M)
    if not m:
        return None
    return {g.strip().lower() for g in m.group(1).split(",") if g.strip() and g.strip().lower() != "none"}


def npc_display(campaign, slug):
    path = npc_path(campaign, slug)
    if os.path.exists(path):
        m = re.search(r"^name:\s*(.+)$", open(path, encoding="utf-8").read(), re.M)
        if m:
            return m.group(1).strip()
    return slug.replace("-", " ").title()


def tiers(campaign, slug):
    """[(tags, text)] from the target's `## who knows` section, or None if absent/untagged."""
    path = npc_path(campaign, slug)
    if not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^## who knows .*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return None
    out = []
    for line in m.group(1).split("\n"):
        b = re.match(r"-\s*\[([^\]]+)\]\s*(.*)", line.strip())
        if b:
            out.append(({t.strip().lower() for t in b.group(1).split(",")}, b.group(2).strip()))
    return out or None


def people_in(campaign, observer, text):
    """Slugs of other NPCs (with files) whose name, first name or surname appears in text."""
    found = []
    for path in sorted(glob.glob(os.path.join("campaigns", campaign, "info", "npcs", "*.md"))):
        slug = os.path.splitext(os.path.basename(path))[0]
        if slug == observer:
            continue
        name = npc_display(campaign, slug)
        words = [w for w in re.findall(r"[A-Za-z']+", name) if len(w) >= 4]
        keys = {name, *(words[:1] + words[-1:])}
        if re.search(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", text, re.I):
            found.append(slug)
    return found


def print_people(campaign, observer, people, show_all=False):
    groups = npc_groups(campaign, observer)
    if groups is None:
        print(f"(!) {observer} has no `groups:` line: only [everyone] tiers are shown")
        groups = set()
    print(f"# Linked facts: what {npc_display(campaign, observer)} knows about people in the scene")
    print(f"(observer groups: {', '.join(sorted(groups)) or 'none'})\n")
    if not people:
        print("- no other known NPC is named in the scene")
    for other in people:
        t = tiers(campaign, other)
        name = npc_display(campaign, other)
        if t is None:
            print(f"- {name}: no tagged `## who knows` section: the NPC agent should NEED; ask the DM")
            continue
        applicable = [txt for tags, txt in t
                      if (show_all or "everyone" in tags or tags & groups) and tags != {"secret"}]
        if applicable:
            for txt in applicable:
                print(f"- {name}: {txt}")
        else:
            print(f"- {name}: nothing in the file says this NPC knows them; the NPC does not recognise them unless told")


def main():
    args = sys.argv[1:]
    if len(args) >= 2 and ("--scene" in args or "--people" in args):
        campaign, observer = args[0], args[1]
        with_ledger = "--with-ledger" in args
        show_all = "--all" in args
        people = []
        if "--scene" in args:
            i = args.index("--scene")
            people += people_in(campaign, observer, args[i + 1] if i + 1 < len(args) else "")
        if "--people" in args:
            i = args.index("--people")
            people += [x for x in (args[i + 1].split(",") if i + 1 < len(args) else []) if x]
        people = list(dict.fromkeys(people))
        print_people(campaign, observer, people, show_all)
        if not with_ledger:
            return
        print()
        args = [campaign, observer]
    if len(args) == 2 and args[1] == "--audit":
        missing = [os.path.splitext(os.path.basename(p))[0]
                   for p in sorted(glob.glob(os.path.join("campaigns", args[0], "info", "npcs", "*.md")))
                   if not re.search(r"^## who knows", open(p, encoding="utf-8").read(), re.M)]
        print(f"{len(missing)} NPC file(s) without a '## who knows' section" + (": " + ", ".join(missing) if missing else ""))
        sys.exit(1 if missing else 0)
    people = []
    if "--people" in args:
        i = args.index("--people")
        people = [x for x in args[i + 1].split(",") if x] if i + 1 < len(args) else []
        del args[i:i + 2]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    campaign, slug = args
    base = os.path.join("campaigns", campaign, "party")
    names = names_for(base, slug)
    pat = pattern(names)
    print(f"# Linked-fact candidates for {slug} (matching: {', '.join(names)})\n")

    print("## Objects (party view)")
    n_obj = 0
    for path in sorted(glob.glob(os.path.join(base, "objects", "*.md"))):
        title, rows = ledger_rows(path)
        hits = [r for r in rows if pat.search(" ".join(r[2:6]))]
        if not hits:
            continue
        n_obj += 1
        last = rows[-1]
        t, _, w = title.partition(" — ")
        print(f"- **{t}**" + (f" — {w}" if w else "") + f"\n  now: holder {last[3]}; {last[4]}; {last[5]}")
        for r in hits:
            role = "holder" if pat.search(r[3]) else "mentioned"
            print(f"  - Session {r[0]} ({role}): {clip(r[2])}")
    if not n_obj:
        print("- none")

    print("\n## Places (party view)")
    n_loc = 0
    for path in sorted(glob.glob(os.path.join(base, "locations", "*.md"))):
        title, rows = ledger_rows(path)
        hits = [r for r in rows if pat.search(" ".join(r[2:5]))]
        if not hits:
            continue
        n_loc += 1
        last = rows[-1]
        t, _, w = title.partition(" — ")
        print(f"- **{t}**" + (f" — {w}" if w else "") + f"\n  now: {last[3]}; {clip(last[4], 120)}")
        for r in hits:
            print(f"  - Session {r[0]}: {clip(r[2])}")
    if not n_loc:
        print("- none")

    print("\n## Relationships (party/relationships.md)")
    rel = os.path.join(base, "relationships.md")
    found = False
    if os.path.exists(rel):
        for l in open(rel, encoding="utf-8").read().split("\n"):
            if l.startswith("|") and pat.search(l) and not l.startswith("| NPC"):
                print("- " + clip(l.strip().strip("|"), 260))
                found = True
    if not found:
        print("- none")

    print("\n## Other NPCs whose memory names this NPC")
    others = []
    for path in sorted(glob.glob(os.path.join(base, "npc-memory", "*.md"))):
        o = os.path.splitext(os.path.basename(path))[0]
        if o != slug and not o.startswith("_") and pat.search(open(path, encoding="utf-8").read()):
            others.append(o)
    print("- " + (", ".join(others) if others else "none"))

    for other in people:
        path = os.path.join("campaigns", campaign, "info", "npcs", other + ".md")
        print(f"\n## Who knows {other}")
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        m = re.search(r"^## who knows .*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        print(m.group(1).strip() if m else "- no section: ask the DM / the NPC agent should NEED")


if __name__ == "__main__":
    main()
