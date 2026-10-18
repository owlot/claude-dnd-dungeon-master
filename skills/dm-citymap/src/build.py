#!/usr/bin/env python3
"""Build legend.json from src/*.txt (key lists) and src/positions.json (map positions).
Run from anywhere: python3 .claude/skills/dm-citymap/src/build.py"""
import json, os, re
here = os.path.dirname(os.path.abspath(__file__))
WARDS = [("sea", "sea.txt"), ("castle", "castle.txt"), ("dock", "dock.txt"), ("north", "north.txt"),
         ("trades", "trades.txt"), ("dead", "cd.txt"), ("south", "south.txt"), ("harbor", "harbor.txt")]
pos = {}
pp = os.path.join(here, "positions.json")
if os.path.exists(pp):
    pos = json.load(open(pp))
out = []
for ward, fn in WARDS:
    col = None; line = 0
    for raw in open(os.path.join(here, fn), encoding="utf-8"):
        raw = raw.rstrip("\n")
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("@col"):
            _, x, y, p = raw.split(); col = (int(x), int(y), int(p)); line = 0; continue
        lines = 1
        m = re.search(r" ##(\d)$", raw)
        if m:
            lines = int(m.group(1)); raw = raw[:m.start()]
        code, name, detail = raw.split("|", 2)
        x, y0, p = col
        y = y0 + line * p + (lines - 1) * p // 2
        line += lines
        e = {"code": code, "ward": ward, "name": name, "detail": detail, "list": [x + 200, y], "pos": None, "conf": None}
        k = ward + ":" + code
        if k in pos:
            e["pos"] = pos[k]["pos"]; e["conf"] = pos[k]["conf"]
            if pos[k].get("also"): e["also"] = pos[k]["also"]
        out.append(e)
open(os.path.join(here, "..", "legend.json"), "w", encoding="utf-8").write("[\n" + ",\n".join(json.dumps(e, ensure_ascii=False) for e in out) + "\n]\n")
n = len(out); print(n, "entries;", sum(1 for e in out if e["pos"]), "with map position")

# inject the data into the page (single file: the page cannot fetch other files)
html_path = os.path.join(here, "..", "citymap.html")
html = open(html_path, encoding="utf-8").read()
rows = []
for e in out:
    r = [e["code"], e["ward"], e["name"], e["detail"], e["list"], e["pos"], e["conf"], e.get("also")]
    while r and r[-1] is None:
        r.pop()
    rows.append(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
block = "[\n" + ",\n".join(rows) + "\n]"
a, b = html.index("/*LEG:START*/") + len("/*LEG:START*/"), html.index("/*LEG:END*/")
open(html_path, "w", encoding="utf-8").write(html[:a] + block + html[b:])
print("page updated,", len(block), "bytes of data")

# street and place names (streets.json -> STREETS block in the page)
sp = os.path.join(here, "..", "streets.json")
if os.path.exists(sp):
    st = json.load(open(sp, encoding="utf-8"))
    srows = [json.dumps([e["name"], e["kind"], e["pos"], e.get("also") or None, e.get("conf")], ensure_ascii=False, separators=(",", ":")) for e in st]
    sblock = "[\n" + ",\n".join(srows) + "\n]"
    html = open(html_path, encoding="utf-8").read()
    a, b = html.index("/*STR:START*/") + len("/*STR:START*/"), html.index("/*STR:END*/")
    open(html_path, "w", encoding="utf-8").write(html[:a] + sblock + html[b:])
    print("streets:", len(st), "names inlined")
