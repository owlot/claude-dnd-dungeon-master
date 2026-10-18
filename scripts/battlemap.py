#!/usr/bin/env python3
"""Battle map helper (see .claude/skills/dm-battlemap/SKILL.md).

The Combat Positions map (served by the table chat at /map/) keeps its board in the map database (doc dm/state). The main
thread copies that document to campaigns/<campaign>/party/battlefield/dm/state.json (the MCP tool map_get with
path dm/state and an out file; the combat-tracker does the same itself). This script works on that local copy:
it answers position questions (summary, dist, area, path, reach) and builds the files to write back.

Commands
  maps <campaign> [query...]       list map images in sources/ (role dm/player/shared, grid size from the file name)
  size <image>                     print "width height" of a jpg/png/webp
  summary <campaign>               positions, distances, melee reach and terrain, from the local copy
  dist <campaign> <A> <B>          distance in feet between two tokens
  move <campaign> "Name=Cell" ...  move tokens (cell like N7) and write battlefield/dm/push.json
  roster <campaign> [--json]       party characters with speed (from the sheet) and website portrait file
  apply-roster <campaign> [assets.json]   set speed, AC, HP, ability scores and attacks (from the sheets) and portraits on the board's party tokens (assets.json: portrait file path -> asset id; omit it to refresh stats and HP only)
  apply-stats <campaign> <stats.json>     set AC, HP and attacks on any token from a JSON file keyed by token name (used for enemies, from the encounter file)
  effects <campaign>               spell effects on the board (cloud of daggers, moonbeam...) and who is inside each
  where <campaign> <token>         which effects a token is standing in (use at the start of its turn)
  effect <campaign> add|remove|presets ...   place or remove a spell effect; writes push.json
  turn <campaign> <token|none> [--speed N] [--round N]   make a token the active turn (resets its movement); writes push.json
  lastmove <campaign>              what was just moved on the table, and the opportunity attacks that route provoked
  init <campaign> <spec.json>      build a complete board (terrain, fog, tokens, maps) and write battlefield/dm/new_state.json
  area <campaign> <shape> ...      who is inside an area of effect (sphere/cylinder, cone, line, cube); see "area" below
  (area, path and reach take --overlay: also write battlefield/dm/overlay.json to highlight the result on the DM's board)
  path <campaign> <token> <cell> [speed]   cheapest route, cost in feet, opportunity attacks it provokes
  reach <campaign> <token> [speed] [--reach 5] [--map]   which squares and which enemies a token can reach (default: movement left)
Cells: column letters + row number, A1 = top-left. 5 ft squares, edge to edge. Diagonals follow the board's rule (default
alternating: the 1st diagonal 5 ft, the 2nd 10 ft, the 3rd 5 ft ...; carried across moves within a turn); the board can switch to flat 5 ft.

area shapes (origin = a cell centre like N7, a corner like N7.br (tl/tr/bl/br), or a token name; direction = N NE E SE S SW W NW,
a cell, or a token to aim at):
  area <c> sphere   <origin> <radius_ft> [--chebyshev]     sphere and cylinder: any part of a creature's square within the radius
  area <c> cone     <origin> <direction> <length_ft>        53-degree cone (width = distance); the caster's own square is excluded
  area <c> line     <origin> <direction> <length_ft> [width_ft=5]
  area <c> cube     <top-left cell> <side_ft>               the cube as a block of squares
Walls and closed doors block: a creature inside the shape but with a wall between it and the origin is listed separately
("behind a wall"); rule on cover or spread yourself. Positions are read from the board only (no elevation).

path / reach: 5 ft per square, diagonals alternate 5/10 ft (board rule), difficult terrain costs double, walls and edges block, no cutting wall corners,
closed doors can be walked through (opening one is a free interaction; the door is reported), you can pass through friends but
not enemies, and you cannot stop on an occupied square. Default melee reach 5 ft.
"""
import json
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from campaign_paths import campaign_dir  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
SIZE_NAMES = {1: "Medium", 2: "Large", 3: "Huge", 4: "Gargantuan"}
TERRAIN = [("wall", "Wall"), ("door", "Closed door"), ("opendoor", "Open door"),
           ("difficult", "Difficult"), ("cover", "Half cover"), ("hazard", "Hazard / water")]


# ---------- cells ----------
def col_name(i):
    s, i = "", i + 1
    while i > 0:
        m = (i - 1) % 26
        s = chr(65 + m) + s
        i = (i - 1) // 26
    return s


def cell_name(x, y):
    return f"{col_name(x)}{y + 1}"


def parse_cell(s):
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", s.strip())
    if not m:
        raise ValueError(f"bad cell '{s}' (expected like N7)")
    n = 0
    for ch in m.group(1).upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1, int(m.group(2)) - 1


# ---------- state file ----------
def state_path(campaign):
    return os.path.join(campaign_dir(campaign), "party", "battlefield", "dm", "state.json")


def load_state(campaign):
    p = state_path(campaign)
    if not os.path.exists(p):
        sys.exit(f"No battlefield copy at {p}. Ask the main thread to sync with the MCP tool map_get (path dm/state, out campaigns/{campaign}/party/battlefield/dm/state.json).")
    raw = json.load(open(p))
    data = raw.get("data", raw)
    global DIAG_ALT
    DIAG_ALT = data.get("diag", "alt") != "flat"
    return data, None


DIAG_ALT = True      # board rule: the 1st diagonal costs 5 ft, the 2nd 10 ft, the 3rd 5 ft ... (set from the board's `diag`)


def squares(a, b):
    """Distance in squares between two footprints, edge to edge, under the board's diagonal rule."""
    gx = max(a["x"] - (b["x"] + b["size"]), b["x"] - (a["x"] + a["size"]))
    gy = max(a["y"] - (b["y"] + b["size"]), b["y"] - (a["y"] + a["size"]))
    ax, ay = max(gx + 1, 0), max(gy + 1, 0)
    return max(ax, ay) + (min(ax, ay) // 2 if DIAG_ALT else 0)


def feet(a, b):
    return squares(a, b) * 5


def fog_at(st, t):
    fog = set(st.get("fog", []))
    return all(f"{t['x'] + dx},{t['y'] + dy}" in fog for dx in range(t["size"]) for dy in range(t["size"]))


def terrain_map(st):
    out = {}
    for s in st.get("terrain", []):
        x, y, k = s.split(",")
        out[(int(x), int(y))] = k
    return out


def terrain_under(st, t):
    tm = terrain_map(st)
    for dx in range(t["size"]):
        for dy in range(t["size"]):
            k = tm.get((t["x"] + dx, t["y"] + dy))
            if k and k not in ("wall", "door", "opendoor"):
                return k
    return None


def build_summary(st):
    tokens = st.get("tokens", [])
    L = [f"BATTLEFIELD rev {st.get('rev', 0)} · Round {st.get('round', 1)} · {st['cols']}x{st['rows']} grid, 5 ft squares, diagonals " + ("alternate 5/10 ft" if st.get("diag", "alt") != "flat" else "5 ft") + " (A1 = top-left, columns letters, rows numbers)", "POSITIONS"]
    for side, label in (("pc", "PARTY"), ("npc", "ALLIES"), ("enemy", "ENEMIES")):
        for t in (x for x in tokens if x["side"] == side):
            flags = []
            if t["size"] > 1:
                flags.append(f"{SIZE_NAMES.get(t['size'], t['size'])}, {t['size']}x{t['size']}")
            if t.get("down"):
                flags.append("DOWN")
            if t.get("hid") and t["side"] == "pc":
                flags.append("hiding (players still see this token, dashed)")
            elif t.get("hid"):
                flags.append("hidden from players")
            elif fog_at(st, t):
                flags.append("in unrevealed area")
            ter = terrain_under(st, t)
            if ter:
                flags.append(f"on {ter}")
            L.append(f"  {label} {t['name']} — {cell_name(t['x'], t['y'])}" + (f" ({'; '.join(flags)})" if flags else ""))
    act = next((t for t in tokens if t["id"] == st.get("active")), None)
    if act:
        sp, mv = int(act.get("speed", 30)), int(act.get("moved", 0))
        L.append(f"ACTIVE TURN: {act['name']} at {cell_name(act['x'], act['y'])} (speed {sp} ft, moved {mv} ft, {max(0, sp - mv)} ft left)")
    lm = st.get("lastMove")
    if lm:
        L.append(f"LAST MOVE (on the table{', out of combat' if lm.get('free') else ''}): {lm['name']} {lm['from']} -> {lm['to']}, {lm['cost']} ft, round {lm.get('round', '?')}")
    allies = [t for t in tokens if t["side"] != "enemy"]
    foes = [t for t in tokens if t["side"] == "enemy"]
    if allies and foes:
        L.append("DISTANCES (ft, edge to edge, diagonals per the board rule)")
        for a in allies:
            L.append(f"  {a['name']} → " + ", ".join(f"{f['name']} {feet(a, f)}" for f in foes))
    adj = []
    for i, a in enumerate(tokens):
        for b in tokens[i + 1:]:
            if squares(a, b) <= 1 and (a["side"] == "enemy") != (b["side"] == "enemy"):
                adj.append(f"{a['name']} ↔ {b['name']}")
    L.append("IN MELEE REACH (5 ft, opposing sides): " + ("; ".join(adj) if adj else "none"))
    by = {}
    for (x, y), k in terrain_map(st).items():
        by.setdefault(k, []).append((x, y))
    parts = []
    for k, label in TERRAIN:
        if k in by:
            cells = [cell_name(x, y) for x, y in sorted(by[k])]
            parts.append(f"{label}: " + " ".join(cells[:40]) + (f" +{len(cells) - 40} more" if len(cells) > 40 else ""))
    L.append("TERRAIN: " + (" | ".join(parts) if parts else "none"))
    fx = st.get("effects") or []
    if fx:
        L.append("SPELL EFFECTS")
        for e in fx:
            try:
                cs = effect_cells(st, e)
                inside = ", ".join(t["name"] for t in tokens_in_effect(st, e, cs)) or "nobody"
            except Exception:
                inside = "?"
            L.append(f"  {e['name']} [{e['id']}] {e['shape']} {e['size']:g} ft" + (f", {e['rounds']} round(s) left" if e.get("rounds") is not None else "") + (" (concentration)" if e.get("conc") else "") + (" [hidden from players]" if e.get("hidden") else "") + f": inside {inside}")
    fogn = len(st.get("fog", []))
    L.append(f"MAP: {'image loaded' if st.get('img') else 'none'} · FOG: {fogn} of {st['cols'] * st['rows']} squares hidden from players")
    return "\n".join(L)


# ---------- images ----------
def image_size(path):
    with open(path, "rb") as f:
        head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            if head[12:16] == b"VP8 ":
                f.seek(26)
                w, h = struct.unpack("<HH", f.read(4))
                return w & 0x3FFF, h & 0x3FFF
            if head[12:16] == b"VP8L":
                f.seek(21)
                b = struct.unpack("<I", f.read(4))[0]
                return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
            if head[12:16] == b"VP8X":
                return (int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1)
        f.seek(0)
        data = f.read()
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seglen
    raise ValueError(f"cannot read the size of {path}")


def classify(name):
    n = name.lower()
    role = "shared"
    if re.search(r"\(?\bdms?\b|dm's|dm\)|\bdms\b|gm", n):
        role = "dm"
    elif "player" in n:
        role = "player"
    grid = "nogrid" if re.search(r"no[ _-]?grid", n) else ("grid" if "grid" in n else "unknown")
    m = re.search(r"(\d+)\s*x\s*(\d+)", n)
    dims = (int(m.group(1)), int(m.group(2))) if m else None
    return role, grid, dims


def cmd_maps(campaign, query):
    root = os.path.join(campaign_dir(campaign), "sources")
    words = [w.lower() for q in query for w in re.split(r"[\s_-]+", q) if w]
    rows = []
    root = os.path.abspath(root)
    for dp, _, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(IMG_EXT):
                continue
            hay = (os.path.relpath(os.path.join(dp, fn), root)).lower()
            score = sum(1 for w in words if w in hay)
            if words and score == 0:
                continue
            role, grid, dims = classify(fn)
            rows.append((score, os.path.join(dp, fn), role, grid, dims))
    rows.sort(key=lambda r: (-r[0], r[1]))
    for score, p, role, grid, dims in rows[:40]:
        try:
            w, h = image_size(p)
            px = f"{w}x{h}px"
        except Exception:
            px = "?"
        d = f"{dims[0]}x{dims[1]} squares" if dims else "squares unknown"
        print(f"{role:7} grid={grid:7} {d:20} {px:12} {p}")
    if not rows:
        print("no matching map images")


# ---------- moves ----------
def cmd_move(campaign, pairs):
    st, version = load_state(campaign)
    tokens = st["tokens"]
    notes = []
    for pair in pairs:
        name, _, cell = pair.partition("=")
        matches = [t for t in tokens if t["name"].lower() == name.strip().lower()] or \
                  [t for t in tokens if t["name"].lower().startswith(name.strip().lower())]
        if len(matches) != 1:
            sys.exit(f"'{name}' matches {len(matches)} tokens: {[t['name'] for t in matches]}")
        t = matches[0]
        x, y = parse_cell(cell)
        if x < 0 or y < 0 or x + t["size"] > st["cols"] or y + t["size"] > st["rows"]:
            sys.exit(f"{cell} is outside the {st['cols']}x{st['rows']} grid for {t['name']} ({t['size']}x{t['size']})")
        tm = terrain_map(st)
        for dx in range(t["size"]):
            for dy in range(t["size"]):
                if tm.get((x + dx, y + dy)) in ("wall", "door"):
                    notes.append(f"WARNING {t['name']} lands on a {tm[(x + dx, y + dy)]} at {cell_name(x + dx, y + dy)}")
        for o in tokens:
            if o is not t and squares({"x": x, "y": y, "size": t["size"]}, o) == 0:
                notes.append(f"WARNING {t['name']} overlaps {o['name']}")
        old = cell_name(t["x"], t["y"])
        t["x"], t["y"] = x, y
        notes.append(f"{t['name']}: {old} -> {cell_name(x, y)}")
    st["rev"] = int(st.get("rev", 0)) + 1
    st["sid"] = "claude"
    st["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    st["summary"] = build_summary(st)
    out = os.path.abspath(os.path.join(os.path.dirname(state_path(campaign)), "push.json"))
    json.dump({k: st[k] for k in ("tokens", "rev", "sid", "updatedAt", "summary")}, open(out, "w"), ensure_ascii=False)
    print("\n".join(notes))
    print(f"\nWrote {out}. Main thread: Apply it: the MCP tool map_set (path dm/state, file {out})")


# ---------- geometry helpers (area / path / reach) ----------
import heapq
import math

DIRS = {"N": (0, -1), "NE": (1, -1), "E": (1, 0), "SE": (1, 1), "S": (0, 1), "SW": (-1, 1), "W": (-1, 0), "NW": (-1, -1)}


def find_token(st, name):
    toks = st["tokens"]
    m = [t for t in toks if t["name"].lower() == name.lower()] or [t for t in toks if t["name"].lower().startswith(name.lower())]
    if len(m) != 1:
        sys.exit(f"'{name}' matches {len(m)} tokens: {[t['name'] for t in m]}")
    return m[0]


def token_center(t):
    return (t["x"] + t["size"] / 2, t["y"] + t["size"] / 2)


def parse_point(st, s):
    """cell centre 'N7', corner 'N7.br', or token name -> (x, y, token_or_None) in square units."""
    m = re.fullmatch(r"([A-Za-z]+\d+)(?:\.(tl|tr|bl|br))?", s.strip())
    if m:
        x, y = parse_cell(m.group(1))
        if not (0 <= x < st["cols"] and 0 <= y < st["rows"]):
            sys.exit(f"{s} is outside the {st['cols']}x{st['rows']} grid")
        c = m.group(2)
        if c is None:
            return x + 0.5, y + 0.5, None
        return x + (1 if c in ("tr", "br") else 0), y + (1 if c in ("bl", "br") else 0), None
    t = find_token(st, s)
    cx, cy = token_center(t)
    return cx, cy, t


def parse_direction(st, origin, s):
    if s.upper() in DIRS:
        dx, dy = DIRS[s.upper()]
    else:
        px, py, _ = parse_point(st, s)
        dx, dy = px - origin[0], py - origin[1]
    n = math.hypot(dx, dy)
    if n == 0:
        sys.exit("direction has zero length (aim at a different square)")
    return dx / n, dy / n


def blockers(st):
    """(walls, closed doors) as sets of (x, y)."""
    walls, doors = set(), set()
    for k, v in terrain_map(st).items():
        if v == "wall":
            walls.add(k)
        elif v == "door":
            doors.add(k)
    return walls, doors


def clear_ray(st, a, b, ignore_cells):
    """True if the straight line a->b (square units) crosses no wall or closed door outside ignore_cells."""
    walls, doors = blockers(st)
    block = walls | doors
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) * 10))
    for i in range(1, n):
        x = a[0] + (b[0] - a[0]) * i / n
        y = a[1] + (b[1] - a[1]) * i / n
        c = (int(math.floor(x)), int(math.floor(y)))
        if c in block and c not in ignore_cells:
            return False
    return True


def footprint(t, x=None, y=None):
    x = t["x"] if x is None else x
    y = t["y"] if y is None else y
    return [(x + dx, y + dy) for dx in range(t["size"]) for dy in range(t["size"])]


def rect_distance(px, py, t):
    dx = max(t["x"] - px, 0, px - (t["x"] + t["size"]))
    dy = max(t["y"] - py, 0, py - (t["y"] + t["size"]))
    return math.hypot(dx, dy)


def report_area(st, title, hits, origin, origin_tok, cells_note=""):
    inside, blocked = [], []
    for t in hits:
        if origin_tok is not None and t is origin_tok:
            continue
        ignore = set(footprint(t)) | (set(footprint(origin_tok)) if origin_tok else set())
        ok = clear_ray(st, origin, token_center(t), ignore)
        (inside if ok else blocked).append(t)

    def line(t):
        flags = []
        if t.get("down"):
            flags.append("down")
        if t.get("hid"):
            flags.append("hidden from players")
        return f"  {t['name']} ({t['side']}) {cell_name(t['x'], t['y'])}" + (f" [{', '.join(flags)}]" if flags else "")

    print(title)
    if cells_note:
        print(cells_note)
    for label, grp in (("IN THE AREA", inside), ("INSIDE THE SHAPE BUT BEHIND A WALL OR CLOSED DOOR (rule on cover)", blocked)):
        print(f"{label}: " + ("none" if not grp else ""))
        for side, nm in (("pc", "party"), ("npc", "allies"), ("enemy", "enemies")):
            g = [t for t in grp if t["side"] == side]
            if g:
                print(f"  {nm}:")
                for t in g:
                    print("  " + line(t))


def overlay_path(campaign):
    return os.path.abspath(os.path.join(os.path.dirname(state_path(campaign)), "overlay.json"))


def write_overlay(campaign, st, label, layers, marks=None):
    """Highlights for the DM's board: layers of squares / a route, and ringed tokens. Written to battlefield/dm/overlay.json;
    the caller then sets database doc dm/overlay from that file (map_set path=dm/overlay file=<that file>)."""
    doc = {"label": label, "boardRev": int(st.get("rev", 0)), "layers": layers, "marks": marks or [],
           "rev": int(time.time()), "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}
    out = overlay_path(campaign)
    json.dump(doc, open(out, "w"), ensure_ascii=False)
    print(f"\nOverlay written to {out}. To show it on the DM's board: map_set path=dm/overlay file={out} "
          "To hide it: set the same document with empty layers.")


def cmd_area(campaign, args):
    st = load_state(campaign)[0]
    flags = [a for a in args if a.startswith("--")]
    if not [a for a in args if not a.startswith("--")]:
        sys.exit("area needs a shape: sphere | cone | line | cube")
    shape, rest = [a for a in args if not a.startswith("--")][0].lower(), [a for a in args if not a.startswith("--")][1:]
    cheb = "--chebyshev" in flags
    toks = st["tokens"]
    ot = None
    origin = (0.0, 0.0)
    if shape in ("sphere", "cylinder", "radius"):
        ox, oy, ot = parse_point(st, rest[0])
        origin = (ox, oy)
        r = float(rest[1]) / 5

        def cell_in(cx, cy):
            probe = {"x": cx, "y": cy, "size": 1}
            if cheb:
                return max(abs(cx + 0.5 - ox) - 0.5, abs(cy + 0.5 - oy) - 0.5, 0) <= r + 1e-9
            return rect_distance(ox, oy, probe) <= r + 1e-9
        title = f"SPHERE/CYLINDER radius {rest[1]} ft from ({rest[0]})" + (" [square-grid distance]" if cheb else " [true circle]")
        skip_origin_tok = None
    elif shape == "cone":
        ox, oy, ot = parse_point(st, rest[0])
        origin = (ox, oy)
        d = parse_direction(st, origin, rest[1])
        length = float(rest[2]) / 5
        cos_half = math.cos(math.atan(0.5))
        own = set(footprint(ot)) if ot is not None else set()

        def cell_in(cx, cy):
            if (cx, cy) in own:
                return False
            vx, vy = cx + 0.5 - ox, cy + 0.5 - oy
            dist = math.hypot(vx, vy)
            return 0 < dist <= length + 1e-9 and (vx * d[0] + vy * d[1]) / dist >= cos_half - 1e-9
        title = f"CONE {rest[2]} ft from ({rest[0]}) toward {rest[1]}"
        skip_origin_tok = ot
    elif shape == "line":
        ox, oy, ot = parse_point(st, rest[0])
        origin = (ox, oy)
        d = parse_direction(st, origin, rest[1])
        length = float(rest[2]) / 5
        half = (float(rest[3]) if len(rest) > 3 else 5.0) / 10
        own = set(footprint(ot)) if ot is not None else set()

        def cell_in(cx, cy):
            if (cx, cy) in own:
                return False
            vx, vy = cx + 0.5 - ox, cy + 0.5 - oy
            along = vx * d[0] + vy * d[1]
            perp = abs(-vx * d[1] + vy * d[0])
            return 0 < along <= length + 0.5 and perp <= half + 1e-9
        title = f"LINE {rest[2]} ft x {rest[3] if len(rest) > 3 else 5} ft from ({rest[0]}) toward {rest[1]}"
        skip_origin_tok = ot
    elif shape == "cube":
        x0, y0 = parse_cell(rest[0])
        n = max(1, round(float(rest[1]) / 5))
        origin = (x0 + n / 2, y0 + n / 2)

        def cell_in(cx, cy):
            return x0 <= cx < x0 + n and y0 <= cy < y0 + n
        title = f"CUBE {rest[1]} ft ({n}x{n} squares) from {cell_name(x0, y0)} to {cell_name(x0 + n - 1, y0 + n - 1)}"
        skip_origin_tok = None
    else:
        sys.exit(f"unknown shape '{shape}'")
    hits = [t for t in toks if (skip_origin_tok is None or t is not skip_origin_tok) and any(cell_in(cx, cy) for (cx, cy) in footprint(t))]
    report_area(st, title, hits, origin, skip_origin_tok)
    if "--overlay" in flags:
        cells = [f"{x},{y}" for x in range(st["cols"]) for y in range(st["rows"]) if cell_in(x, y)]
        marks = [f"{t['x']},{t['y']}" for t in hits]
        write_overlay(campaign, st, title, [{"kind": "area", "label": title, "cells": cells}], marks)


# ---------- movement ----------
def move_graph(st, tok):
    walls, doors = blockers(st)
    tm = terrain_map(st)
    cols, rows = st["cols"], st["rows"]
    others = [o for o in st["tokens"] if o is not tok]
    hostile = [o for o in others if (o["side"] == "enemy") != (tok["side"] == "enemy") and not o.get("down")]
    hostile_cells = set(c for o in hostile for c in footprint(o))
    occupied = set(c for o in others for c in footprint(o))

    def fits(x, y):
        if x < 0 or y < 0 or x + tok["size"] > cols or y + tok["size"] > rows:
            return False
        fp = footprint(tok, x, y)
        return not any(c in walls or c in hostile_cells for c in fp)

    def diff_mult(x, y):
        fp = footprint(tok, x, y)
        return 2 if any(tm.get(c) == "difficult" for c in fp) else 1

    def dijkstra():
        """Cheapest cost to every square. With the alternating diagonal rule the cost of a diagonal step depends on how many
        diagonals came before it (including earlier moves this turn, kept as the token's `dpar`), so the search runs over
        (x, y, parity). Returns (cost per square, predecessor per state, best parity per square)."""
        p0 = int(tok.get("dpar", 0)) % 2 if DIAG_ALT else 0
        start = (tok["x"], tok["y"], p0)
        dist, prev = {start: 0}, {}
        pq = [(0, start)]
        while pq:
            d, (x, y, p) = heapq.heappop(pq)
            if d > dist.get((x, y, p), 1e9):
                continue
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not dx and not dy:
                        continue
                    nx, ny = x + dx, y + dy
                    if not fits(nx, ny):
                        continue
                    if dx and dy and not (fits(x + dx, y) and fits(x, y + dy)):
                        continue                      # no cutting wall corners
                    diag = bool(dx and dy and DIAG_ALT)
                    base = (5 if p == 0 else 10) if diag else 5
                    npar = (1 - p) if diag else p
                    nd = d + base * diff_mult(nx, ny)
                    key = (nx, ny, npar)
                    if nd < dist.get(key, 1e9):
                        dist[key] = nd
                        prev[key] = (x, y, p)
                        heapq.heappush(pq, (nd, key))
        cells, par = {}, {}
        for (x, y, p), c in sorted(dist.items(), key=lambda kv: (kv[1], kv[0][2])):
            if (x, y) not in cells:
                cells[(x, y)], par[(x, y)] = c, p
        return cells, prev, par

    return dijkstra, hostile, occupied, doors, tm


def reach_squares(reach_ft):
    return max(1, int(round(reach_ft / 5)))


def in_reach(h, tok, x, y, rsq):
    probe = {"x": x, "y": y, "size": tok["size"]}
    return squares(probe, h) <= rsq


def cmd_path(campaign, args, st=None):
    st = st if st is not None else load_state(campaign)[0]
    tok = find_token(st, args[0])
    gx, gy = parse_cell(args[1])
    speed = float(args[2]) if len(args) > 2 and not args[2].startswith("--") else 30.0
    rft = 5.0
    if "--reach" in args:
        rft = float(args[args.index("--reach") + 1])
    dijkstra, hostile, occupied, doors, tm = move_graph(st, tok)
    dist, prev, par = dijkstra()
    if (gx, gy) not in dist:
        print(f"{tok['name']} cannot get to {cell_name(gx, gy)}: walled off, off the grid, or blocked by enemies.")
        return
    cur = (gx, gy, par[(gx, gy)])
    path = [(gx, gy)]
    while cur in prev:
        cur = prev[cur]
        path.append((cur[0], cur[1]))
    path.reverse()
    cost = dist[(gx, gy)]
    diff = sum(1 for (x, y) in path[1:] if any(tm.get(c) == "difficult" for c in footprint(tok, x, y)))
    haz = [cell_name(x, y) for (x, y) in path[1:] if any(tm.get(c) == "hazard" for c in footprint(tok, x, y))]
    dr = [cell_name(*c) for (x, y) in path[1:] for c in footprint(tok, x, y) if c in doors]
    rsq = reach_squares(rft)
    oa = []
    for i in range(1, len(path)):
        (ax, ay), (bx, by) = path[i - 1], path[i]
        for hst in hostile:
            if in_reach(hst, tok, ax, ay, rsq) and not in_reach(hst, tok, bx, by, rsq):
                oa.append(f"{hst['name']} (leaving {cell_name(ax, ay)} for {cell_name(bx, by)})")
    print(f"{tok['name']}: {cell_name(tok['x'], tok['y'])} -> {cell_name(gx, gy)}")
    print(f"  cost: {int(cost)} ft" + (f" (speed {int(speed)}: {'within speed' if cost <= speed else 'TOO FAR by ' + str(int(cost - speed)) + ' ft; Dash would cover it' if cost <= 2 * speed else 'TOO FAR even with a Dash'})"))
    print("  route: " + " ".join(cell_name(x, y) for (x, y) in path))
    if diff:
        print(f"  difficult terrain: {diff} square(s) entered (cost doubled)")
    if dr:
        print(f"  passes closed door(s): {', '.join(dict.fromkeys(dr))} (opening is a free interaction)")
    if haz:
        print(f"  hazard squares crossed: {', '.join(haz)}")
    print("  provokes opportunity attacks from: " + ("; ".join(oa) if oa else "none") + (" (unless it Disengages)" if oa else ""))
    if cost > 5 and oa:
        print("  note: a different route may avoid some of these; ask for 'path' to a nearer square.")
    if "--overlay" in args:
        title = f"PATH {tok['name']} {cell_name(tok['x'], tok['y'])} to {cell_name(gx, gy)}: {int(cost)} ft" + ("" if cost <= speed else " (over speed)")
        write_overlay(campaign, st, title, [{"kind": "path", "label": title, "cells": [f"{x},{y}" for (x, y) in path]}],
                      [f"{hst['x']},{hst['y']}" for hst in hostile if any(hst['name'] in s for s in oa)])


def cmd_reach(campaign, args):
    st = load_state(campaign)[0]
    tok = find_token(st, args[0])
    speed = float(args[1]) if len(args) > 1 and not args[1].startswith("--") else float(max(0, tok.get("speed", 30) - tok.get("moved", 0)))
    rft = float(args[args.index("--reach") + 1]) if "--reach" in args else 5.0
    dijkstra, hostile, occupied, doors, tm = move_graph(st, tok)
    dist, _, _ = dijkstra()
    ok = {p: c for p, c in dist.items() if c <= speed}
    stops = {p: c for p, c in ok.items() if not any(cc in occupied for cc in footprint(tok, *p))}
    print(f"{tok['name']} at {cell_name(tok['x'], tok['y'])}, speed {int(speed)} ft: {len(stops)} squares to stop on (melee reach {int(rft)} ft)")
    rsq = reach_squares(rft)
    foes = [o for o in st["tokens"] if (o["side"] == "enemy") != (tok["side"] == "enemy") and not o.get("down")]
    print("MELEE THIS TURN (cheapest square to attack from):")
    for o in foes:
        best = None
        for p, c in stops.items():
            if in_reach(o, tok, p[0], p[1], rsq) and (best is None or c < best[1]):
                best = (p, c)
        if best:
            note = " (already in reach)" if best[1] == 0 else ""
            print(f"  {o['name']} {cell_name(o['x'], o['y'])}: yes, from {cell_name(*best[0])}, {int(best[1])} ft of movement{note}")
        else:
            near = min(dist.items(), key=lambda kv: (squares({'x': kv[0][0], 'y': kv[0][1], 'size': tok['size']}, o), kv[1]))
            print(f"  {o['name']} {cell_name(o['x'], o['y'])}: no, not within {int(speed)} ft of movement (closest it gets: {cell_name(*near[0])}, {int(near[1])} ft)")
    if "--overlay" in args:
        title = f"REACH {tok['name']} {int(speed)} ft"
        marks = []
        for o in foes:
            if any(in_reach(o, tok, p[0], p[1], rsq) for p in stops):
                marks.append(f"{o['x']},{o['y']}")
        write_overlay(campaign, st, title, [{"kind": "reach", "label": title, "cells": [f"{x},{y},{int(c)}" for (x, y), c in sorted(stops.items())]}], marks)
    if "--map" in args:
        print("MAP  @ you  digit = cost/5 to stand there (capped 9)  # wall  + closed door  ~ difficult  X enemy  a ally  . out of reach")
        tokcells = {c: o for o in st["tokens"] for c in footprint(o)}
        walls, dset = blockers(st)
        head = "    " + "".join(col_name(x)[-1] for x in range(st["cols"]))
        print(head)
        for y in range(st["rows"]):
            row = ""
            for x in range(st["cols"]):
                c = (x, y)
                if c in footprint(tok):
                    row += "@"
                elif c in tokcells:
                    row += "X" if tokcells[c]["side"] == "enemy" else "a"
                elif c in walls:
                    row += "#"
                elif c in dset:
                    row += "+"
                elif c in ok:
                    row += str(min(9, ok[c] // 5))
                elif tm.get(c) == "difficult":
                    row += "~"
                else:
                    row += "."
            print(f"{y + 1:>3} {row}")


# ---------- roster: speed from the character sheet, portrait from the website images ----------
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def read_sheet(path):
    txt = open(path, encoding="utf-8").read()
    g = lambda k: (re.search(rf"^{k}:\s*(.+)$", txt, re.M) or [None, None])[1]
    name = g("name") or (re.search(r"^# (.+)$", txt, re.M) or [None, os.path.basename(path)[:-3]])[1]
    speed = None
    m = re.search(r"\|\s*\*\*Speed\*\*\s*\|\s*(\d+)", txt)
    if m:
        speed = int(m.group(1))
    typ = (g("type") or "").strip().lower()
    if not typ:
        m = re.search(r"\|\s*\*\*Type\*\*\s*\|\s*([^|]+)\|", txt)
        typ = "npc" if m and "npc" in m.group(1).lower() else "pc"
    ref = g("reference")
    out = {"name": name.strip(), "slug": g("slug") or slugify(name), "speed": speed, "type": typ, "reference": ref.strip() if ref else None}
    out.update(read_stats(txt))
    return out


def read_stats(txt):
    """AC, HP (max, current, temporary), ability scores, attacks and spell numbers from a character sheet's tables."""
    def num(label):
        m = re.search(r"\|\s*\*\*" + label + r"\*\*\s*\|[^|\d-]*(-?\d+)", txt)
        return int(m.group(1)) if m else None
    r = {}
    for key, label in (("ac", "Armor Class"), ("maxhp", "HP Maximum"), ("hp", "Current HP"), ("thp", "Temporary HP")):
        v = num(label)
        if v is not None:
            r[key] = v
    abil = {}
    for full, short in (("Strength", "STR"), ("Dexterity", "DEX"), ("Constitution", "CON"), ("Intelligence", "INT"), ("Wisdom", "WIS"), ("Charisma", "CHA")):
        m = re.search(r"^\|\s*" + full + r"\s*\|\s*(\d+)\s*\|\s*([+-]?\d+)", txt, re.M)
        if m:
            abil[short] = [int(m.group(1)), int(m.group(2))]
    attacks = []
    m = re.search(r"^## Attacks\s*\n(.*?)(?=^## |\Z)", txt, re.M | re.S)
    if m:
        for ln in m.group(1).splitlines():
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if ln.lstrip().startswith("|") and len(c) >= 4 and c[0] not in ("Name", "") and not set(c[0]) <= set("-: "):
                attacks.append({"n": c[0], "b": c[1], "d": c[2], "t": c[3], "note": c[4] if len(c) > 4 else ""})
    notes = []
    for label, pat in (("Proficiency", r"\*\*Proficiency Bonus:\*\*\s*(\+?\d+)"), ("Passive Perception", r"\*\*Passive Perception:\*\*\s*(\d+)"),
                       ("Spell save DC", r"\*\*Spell Save DC\*\*\s*\|\s*(\d+)"), ("Spell attack", r"\*\*Spell Attack Bonus\*\*\s*\|\s*(\+?\d+)")):
        mm = re.search(pat, txt)
        if mm:
            notes.append([label, mm.group(1)])
    if abil or attacks:
        r["info"] = {"abil": abil, "attacks": attacks, "facts": notes}
    return r


def find_portrait(campaign, slug, name, ref=None):
    """Website image for a character: the sheet's `## image reference:`, then world-images/npcs/<slug>, then images/<first name>."""
    site = os.path.join(REPO, "website", campaign)
    cands = []
    if ref:
        cands.append(os.path.join(REPO, ref))
    first = slugify(name.split()[0]) if name.split() else slug
    for base in (os.path.join(site, "assets", "world-images", "npcs", slug), os.path.join(site, "images", slug), os.path.join(site, "images", first)):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            cands.append(base + ext)
    npc = os.path.join(campaign_dir(campaign), "info", "npcs", slug + ".md")
    if os.path.exists(npc):
        m = re.search(r"^reference:\s*(.+)$", open(npc, encoding="utf-8").read(), re.M)
        if m:
            cands.insert(0, os.path.join(REPO, m.group(1).strip()))
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def load_roster(campaign):
    d = os.path.join(campaign_dir(campaign), "party", "characters")
    out = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".md"):
            continue
        s = read_sheet(os.path.join(d, fn))
        s["portrait"] = find_portrait(campaign, s["slug"], s["name"], s["reference"])
        s["side"] = "npc" if s["type"] == "npc" else "pc"
        out.append(s)
    return out


def roster_match(roster, tokname):
    n = tokname.lower()
    for r in roster:
        if r["name"].lower() == n or r["slug"] == slugify(tokname):
            return r
    m = [r for r in roster if r["name"].lower().startswith(n) or n.startswith(r["name"].lower().split()[0])]
    return m[0] if len(m) == 1 else None


def cmd_roster(campaign, as_json):
    ro = load_roster(campaign)
    if as_json:
        print(json.dumps([{k: r[k] for k in ("name", "slug", "side", "speed", "portrait")} for r in ro], indent=1))
        return
    for r in ro:
        print(f"{r['name']:22} {r['side']:4} speed {str(r['speed'] or '?'):>3} ft  portrait: {r['portrait'] or 'none found'}")


def write_push(campaign, st, keys=("tokens",)):
    st["rev"] = int(st.get("rev", 0)) + 1
    st["sid"] = "claude"
    st["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    st["summary"] = build_summary(st)
    out = os.path.abspath(os.path.join(os.path.dirname(state_path(campaign)), "push.json"))
    json.dump({k: st[k] for k in tuple(keys) + ("rev", "sid", "updatedAt", "summary")}, open(out, "w"), ensure_ascii=False)
    return out


def cmd_apply_stats(campaign, stats_path):
    """Set AC, HP and attacks on tokens from a JSON file: {"Token name or id": {ac, hp, maxhp, thp, speed, info: {abil, attacks, facts}}}.
    The combat tracker writes this from the encounter file for enemies; party sheets come from apply-roster."""
    st = load_state(campaign)[0]
    data = json.load(open(stats_path))
    notes = []
    for t in st["tokens"]:
        v = data.get(t["name"]) or data.get(t["id"])
        if not v:
            continue
        for k in ("ac", "hp", "maxhp", "thp", "speed", "info"):
            if k in v:
                t[k] = v[k]
        notes.append(f"{t['name']}: AC {t.get('ac', '?')}, HP {t.get('hp', '?')}/{t.get('maxhp', '?')}")
    out = write_push(campaign, st)
    print("\n".join(notes) or "no tokens matched")
    print(f"\nWrote {out}. Apply it: the MCP tool map_set (path dm/state, file {out})")


def cmd_apply_roster(campaign, assets_path=None):
    st = load_state(campaign)[0]
    assets = json.load(open(assets_path)) if assets_path else {}
    ro = load_roster(campaign)
    notes = []
    for t in st["tokens"]:
        r = roster_match(ro, t["name"])
        if not r:
            continue
        if r["speed"]:
            t["speed"] = r["speed"]
        for k in ("ac", "hp", "maxhp", "thp", "info"):
            if k in r:
                t[k] = r[k]
        aid = assets.get(r["portrait"]) if r["portrait"] else None
        if aid:
            t["portrait"] = aid
        notes.append(f"{t['name']}: speed {t.get('speed', 30)} ft, AC {t.get('ac', '?')}, HP {t.get('hp', '?')}/{t.get('maxhp', '?')}, portrait {'set' if aid else 'unchanged'}")
    out = write_push(campaign, st)
    print("\n".join(notes) or "no tokens matched the party roster")
    print(f"\nWrote {out}. Apply it: the MCP tool map_set (path dm/state, file {out})")


# ---------- spell effects (persistent areas: cloud of daggers, moonbeam, fog...) ----------
PRESET_FILE = os.path.join(REPO, ".claude", "skills", "dm-battlemap", "spell-effects.json")


def load_presets():
    return {p["key"]: p for p in json.load(open(PRESET_FILE))["presets"]}


def effect_origin(st, e):
    """Origin point in squares. An effect that follows a caster is centred on that token."""
    if e.get("follow") and e.get("owner"):
        t = next((x for x in st["tokens"] if x["id"] == e["owner"]), None)
        if t:
            return token_center(t)
    return float(e["ox"]), float(e["oy"])


def effect_cells(st, e):
    """Squares affected: a square counts when its CENTRE is inside the shape or on its edge. An origin on a crossing
    (integer coordinates) puts a 5 ft cube or 5 ft radius over the 4 squares around it; an origin on a square centre (x.5)
    puts it over that square (a 5 ft radius also takes the 4 neighbours it touches)."""
    ox, oy = effect_origin(st, e)
    size = float(e["size"]) / 5.0
    eps = 1e-9
    out = []
    shape = e["shape"]
    ang = math.radians(float(e.get("ang", 0)))
    d = (math.cos(ang), math.sin(ang))
    own = set(footprint(next((x for x in st["tokens"] if x["id"] == e.get("owner")), None))) if (e.get("owner") and shape in ("cone", "line") and next((x for x in st["tokens"] if x["id"] == e.get("owner")), None)) else set()
    cos_half = math.cos(math.atan(0.5))
    half_w = float(e.get("width", 5)) / 10.0
    for cx in range(st["cols"]):
        for cy in range(st["rows"]):
            vx, vy = cx + 0.5 - ox, cy + 0.5 - oy
            if shape in ("sphere", "cylinder"):
                ok = math.hypot(vx, vy) <= size + eps
            elif shape == "cube":
                ok = abs(vx) <= size / 2 + eps and abs(vy) <= size / 2 + eps
            elif shape == "cone":
                dist = math.hypot(vx, vy)
                ok = (cx, cy) not in own and 0 < dist <= size + eps and (vx * d[0] + vy * d[1]) / dist >= cos_half - eps
            elif shape == "line":
                along = vx * d[0] + vy * d[1]
                perp = abs(-vx * d[1] + vy * d[0])
                ok = (cx, cy) not in own and 0 < along <= size + 0.5 + eps and perp <= half_w + eps
            else:
                ok = False
            if ok:
                out.append((cx, cy))
    return out


def tokens_in_effect(st, e, cells=None):
    cs = set(cells if cells is not None else effect_cells(st, e))
    return [t for t in st["tokens"] if any(c in cs for c in footprint(t))]


def effect_line(st, e):
    cells = effect_cells(st, e)
    inside = tokens_in_effect(st, e, cells)
    ox, oy = effect_origin(st, e)
    on = "crossing" if abs(ox - round(ox)) < 1e-9 and abs(oy - round(oy)) < 1e-9 else "square centre" if abs(ox - math.floor(ox) - .5) < 1e-9 and abs(oy - math.floor(oy) - .5) < 1e-9 else "point"
    where = f"{ox:g},{oy:g} ({on})"
    meta = []
    if e.get("rounds") is not None:
        meta.append(f"{e['rounds']} round(s) left")
    if e.get("conc"):
        meta.append("concentration" + (f" ({e.get('ownerName') or e.get('owner')})" if e.get("owner") else ""))
    if e.get("follow"):
        meta.append("moves with the caster")
    if e.get("hidden"):
        meta.append("HIDDEN from players")
    names = ", ".join(t["name"] + (" [hidden]" if t.get("hid") else "") for t in inside) or "nobody"
    return (f"{e['name']} [{e['id']}]: {e['shape']} {e['size']:g} ft at {where}, {len(cells)} squares" + (f", {'; '.join(meta)}" if meta else "") +
            f"\n    inside: {names}" + (f"\n    note: {e['note']}" if e.get("note") else ""))


def cmd_effects(campaign):
    st = load_state(campaign)[0]
    es = st.get("effects") or []
    if not es:
        print("No spell effects on the board.")
        return
    for e in es:
        print(effect_line(st, e))


def cmd_where(campaign, name):
    st = load_state(campaign)[0]
    tok = find_token(st, name)
    hit = [e for e in (st.get("effects") or []) if any(c in set(effect_cells(st, e)) for c in footprint(tok))]
    if not hit:
        print(f"{tok['name']} ({cell_name(tok['x'], tok['y'])}) is not in any spell effect.")
        return
    print(f"{tok['name']} ({cell_name(tok['x'], tok['y'])}) is in:")
    for e in hit:
        print(f"  {e['name']} [{e['id']}]" + (" [hidden]" if e.get("hidden") else "") + (f": {e['note']}" if e.get("note") else ""))


def cmd_effect(campaign, args):
    sub = args[0] if args else ""
    presets = load_presets()
    if sub == "presets":
        for k, p in presets.items():
            print(f"{k:18} {p['shape']:6} {p['size']:>4} ft  {'conc ' if p.get('conc') else '     '}{p['rounds']:>4} rounds  [{p['source']}]")
        return
    st = load_state(campaign)[0]
    effects = st.setdefault("effects", [])
    flags = {}
    rest = []
    i = 1
    while i < len(args):
        a = args[i]
        if a in ("--hidden", "--follow", "--conc"):
            flags[a[2:]] = True
        elif a.startswith("--") and i + 1 < len(args):
            flags[a[2:]] = args[i + 1]
            i += 1
        else:
            rest.append(a)
        i += 1
    if sub == "add":
        p = presets.get(flags.get("preset", ""), {})
        if flags.get("preset") and not p:
            sys.exit(f"unknown preset '{flags['preset']}' (run: effect {campaign} presets)")
        shape = flags.get("shape", p.get("shape"))
        size = float(flags.get("size", p.get("size", 0)) or 0)
        if not shape or not size:
            sys.exit("effect add needs --preset KEY or --shape and --size")
        caster = find_token(st, flags["caster"]) if flags.get("caster") else None
        follow = bool(flags.get("follow", p.get("follow", False)))
        if flags.get("origin"):
            ox, oy, _ = parse_point(st, flags["origin"])
        elif caster is not None:
            ox, oy = token_center(caster)
        else:
            sys.exit("effect add needs --origin (N7 = square centre, N7.br = a crossing) or --caster")
        ang = 0.0
        if flags.get("dir"):
            dname = flags["dir"].upper()
            if dname in DIRS:
                dx, dy = DIRS[dname]
            else:
                try:
                    ang = float(flags["dir"])
                    dx = dy = None
                except ValueError:
                    px, py, _ = parse_point(st, flags["dir"])
                    dx, dy = px - ox, py - oy
            if dx is not None:
                ang = math.degrees(math.atan2(dy, dx))
        base = slugify(flags.get("name", p.get("name", "effect")))
        eid = base
        n = 2
        while any(e["id"] == eid for e in effects):
            eid = f"{base}-{n}"
            n += 1
        e = {"id": eid, "name": flags.get("name", p.get("name", "Effect")), "shape": shape, "size": size, "ox": ox, "oy": oy, "ang": round(ang, 2),
             "kind": p.get("kind", "utility"), "rounds": int(flags["rounds"]) if flags.get("rounds") else p.get("rounds"),
             "conc": bool(flags.get("conc", p.get("conc", False))), "follow": follow, "hidden": bool(flags.get("hidden")),
             "note": flags.get("note", p.get("note", "")), "by": "claude"}
        if p.get("width") or flags.get("width"):
            e["width"] = float(flags.get("width", p.get("width", 5)))
        if caster is not None:
            e["owner"], e["ownerName"] = caster["id"], caster["name"]
        effects.append(e)
        print(f"Added {e['name']} [{eid}].")
        print(effect_line(st, e))
    elif sub == "remove":
        key = (rest[0] if rest else "").lower()
        hit = [e for e in effects if e["id"] == key or e["name"].lower() == key]
        if not hit:
            sys.exit(f"no effect '{key}' (ids: {[e['id'] for e in effects]})")
        for e in hit:
            effects.remove(e)
        print("Removed " + ", ".join(e["name"] for e in hit) + ".")
    else:
        sys.exit("effect add|remove|presets ...")
    st["rev"] = int(st.get("rev", 0)) + 1
    st["sid"] = "claude"
    st["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    st["summary"] = build_summary(st)
    out = os.path.abspath(os.path.join(os.path.dirname(state_path(campaign)), "push.json"))
    json.dump({"effects": effects if effects else [], "rev": st["rev"], "sid": "claude", "updatedAt": st["updatedAt"], "summary": st["summary"]}, open(out, "w"), ensure_ascii=False)
    print(f"\nWrote {out}. Apply it: the MCP tool map_set (path dm/state, file {out})")


# ---------- turns and the last table move ----------
def cmd_turn(campaign, args):
    st = load_state(campaign)[0]
    who = args[0]
    pushed = {"rev": int(st.get("rev", 0)) + 1, "sid": "claude", "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}
    if who.lower() in ("none", "off", "clear"):
        st.pop("active", None)
        st.pop("lastMove", None)
        st["combat"] = False
        pushed["combat"] = False
        pushed["active"] = {"__delete__": True}
        pushed["lastMove"] = {"__delete__": True}
        msg = "No active turn."
    else:
        tok = find_token(st, who)
        if "--round" in args:
            nr = int(args[args.index("--round") + 1])
            steps = max(0, nr - int(st.get("round", 1)))
            st["round"] = nr
            pushed["round"] = nr
            if steps and st.get("effects"):
                kept, gone = [], []
                for e in st["effects"]:
                    if e.get("rounds") is None:
                        kept.append(e)
                        continue
                    e["rounds"] = int(e["rounds"]) - steps
                    (kept if e["rounds"] > 0 else gone).append(e)
                st["effects"] = kept
                pushed["effects"] = kept
                if gone:
                    print("Expired: " + ", ".join(e["name"] for e in gone))
        if "--speed" in args:
            tok["speed"] = int(args[args.index("--speed") + 1])
        tok["moved"] = 0
        tok["dpar"] = 0
        st["active"] = tok["id"]
        st["combat"] = True
        pushed["combat"] = True
        st.pop("lastMove", None)
        pushed["active"] = tok["id"]
        pushed["lastMove"] = {"__delete__": True}
        msg = f"Active turn: {tok['name']} at {cell_name(tok['x'], tok['y'])}, speed {tok.get('speed', 30)} ft, movement reset."
    st["rev"], st["sid"], st["updatedAt"] = pushed["rev"], pushed["sid"], pushed["updatedAt"]
    pushed["tokens"] = st["tokens"]
    pushed["summary"] = build_summary(st)
    out = os.path.abspath(os.path.join(os.path.dirname(state_path(campaign)), "push.json"))
    json.dump(pushed, open(out, "w"), ensure_ascii=False)
    print(msg)
    print(f"\nWrote {out}. Main thread / tracker: Apply it: the MCP tool map_set (path dm/state, file {out})")


def before_tok(state, tid):
    return next(t for t in state["tokens"] if t["id"] == tid)


def cmd_lastmove(campaign):
    st = load_state(campaign)[0]
    lm = st.get("lastMove")
    if not lm:
        print("No move recorded on the table since the last turn started.")
        return
    tok = next((t for t in st["tokens"] if t["id"] == lm["id"]), None)
    if tok is None:
        print("The token that moved is no longer on the board.")
        return
    if lm.get("free"):
        print(f"LAST MOVE (out of combat, not counted): {lm['name']} {lm['from']} -> {lm['to']}, {lm['cost']} ft of walking.")
    else:
        print(f"LAST MOVE: {lm['name']} {lm['from']} -> {lm['to']}, {lm['cost']} ft used, {lm.get('left', '?')} ft left (round {lm.get('round', '?')}).")
    print("Opportunity attacks below assume the cheapest route; if the player took a different one, ask the DM.")
    before = json.loads(json.dumps(st))
    for t in before["tokens"]:
        if t["id"] == lm["id"]:
            t["x"], t["y"] = lm["fx"], lm["fy"]
            t["dpar"] = lm.get("dp0", 0)
    cmd_path(campaign, [lm["name"], lm["to"], str(max(lm["cost"], 5))], before)
    # spell effects the mover ended up in (entering an area on a turn usually triggers it)
    for e in (st.get("effects") or []):
        cells = set(effect_cells(st, e))
        was = any(c in cells for c in footprint(before_tok(before, lm["id"])))
        now = any(c in cells for c in footprint(tok))
        if now and not was:
            print(f"ENTERED {e['name']} [{e['id']}]" + (" [hidden from players]" if e.get("hidden") else "") + (f": {e['note']}" if e.get("note") else ""))
        elif was and not now:
            print(f"LEFT {e['name']} [{e['id']}]")


# ---------- init ----------
def expand(cells):
    """['J3', 'K1:K4', 'A1:C2'] -> set of (x, y); a range is a filled rectangle."""
    out = set()
    for c in cells:
        if ":" in c:
            a, b = c.split(":")
            (x0, y0), (x1, y1) = parse_cell(a), parse_cell(b)
            for x in range(min(x0, x1), max(x0, x1) + 1):
                for y in range(min(y0, y1), max(y0, y1) + 1):
                    out.add((x, y))
        else:
            out.add(parse_cell(c))
    return out


def cmd_init(campaign, spec_path):
    spec = json.load(open(spec_path))
    cols, rows = int(spec["cols"]), int(spec["rows"])
    terrain = {}
    for kind, key in (("difficult", "difficult"), ("cover", "cover"), ("hazard", "hazard"), ("wall", "walls"), ("door", "doors"), ("opendoor", "opendoors")):
        for (x, y) in expand(spec.get(key, [])):
            if not (0 <= x < cols and 0 <= y < rows):
                sys.exit(f"{cell_name(x, y)} is outside the {cols}x{rows} grid ({key})")
            terrain[(x, y)] = kind
    # fog: everything hidden, then flood-reveal the starting rooms (stops at walls and closed doors)
    fog = {(x, y) for x in range(cols) for y in range(rows)} if spec.get("fog", "all") == "all" else set()
    block = lambda p: terrain.get(p) in ("wall", "door")
    for c in spec.get("reveal_rooms_from", []):
        q, seen = [parse_cell(c)], set()
        while q:
            p = q.pop()
            if p in seen or p not in fog and p != parse_cell(c) or block(p) or not (0 <= p[0] < cols and 0 <= p[1] < rows):
                continue
            seen.add(p)
            q += [(p[0] + dx, p[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        fog -= seen
        for (x, y) in seen:      # the walls and doors around a revealed room are visible too
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if terrain.get((x + dx, y + dy)) in ("wall", "door"):
                        fog.discard((x + dx, y + dy))
    for r in spec.get("reveal", []):
        fog -= expand([r])
    tokens, used = [], set()
    roster = load_roster(campaign)
    counts = {}
    for t in spec.get("tokens", []):
        counts[t["name"]] = counts.get(t["name"], 0) + 1
    seq = {}
    for t in spec.get("tokens", []):                      # repeated names become "Duergar 1", "Duergar 2"
        if counts[t["name"]] > 1:
            seq[t["name"]] = seq.get(t["name"], 0) + 1
            t["name"] = f"{t['name']} {seq[t['name']]}"
    for i, t in enumerate(spec.get("tokens", [])):
        x, y = parse_cell(t["at"])
        size = int(t.get("size", 1))
        if x + size > cols or y + size > rows:
            sys.exit(f"{t['name']} at {t['at']} does not fit the grid")
        tid = t.get("id") or re.sub(r"[^a-z0-9]+", "-", t["name"].lower()).strip("-")
        while tid in used:
            tid += "-x"
        used.add(tid)
        tokens.append({"id": tid, "name": t["name"], "side": t.get("side", "enemy"), "size": size, "x": x, "y": y,
                       "down": False, "hid": bool(t.get("hid", t.get("side", "enemy") == "enemy")),
                       "speed": int(t.get("speed") or ((roster_match(roster, t["name"]) or {}).get("speed") if t.get("side", "enemy") != "enemy" else None) or 30), "moved": 0,
                       **({"portrait": t["portrait"]} if t.get("portrait") else {})})
    st = {"cols": cols, "rows": rows, "round": 1, "rev": int(spec.get("rev", 1)), "grid": spec.get("grid", True),
          "img": spec.get("img"), "dmImg": spec.get("dmImg"), "sid": "claude", "diag": spec.get("diag", "alt"),
          "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
          "terrain": [f"{x},{y},{k}" for (x, y), k in sorted(terrain.items())],
          "fog": [f"{x},{y}" for (x, y) in sorted(fog)], "tokens": tokens}
    st["summary"] = build_summary(st)
    out = os.path.abspath(os.path.join(os.path.dirname(state_path(campaign)), "new_state.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(st, open(out, "w"), ensure_ascii=False)
    print(st["summary"])
    print(f"\nWrote {out}: {len(terrain)} terrain cells, {len(fog)} hidden squares, {len(tokens)} tokens.")


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = argv[1]
    if cmd == "size":
        print(*image_size(argv[2]))
    elif cmd == "maps":
        cmd_maps(argv[2], argv[3:])
    elif cmd == "summary":
        print(build_summary(load_state(argv[2])[0]))
    elif cmd == "dist":
        st = load_state(argv[2])[0]
        find = lambda n: next(t for t in st["tokens"] if t["name"].lower().startswith(n.lower()))
        a, b = find(argv[3]), find(argv[4])
        print(f"{a['name']} ({cell_name(a['x'], a['y'])}) to {b['name']} ({cell_name(b['x'], b['y'])}): {feet(a, b)} ft")
    elif cmd == "move":
        cmd_move(argv[2], argv[3:])
    elif cmd == "init":
        cmd_init(argv[2], argv[3])
    elif cmd == "roster":
        cmd_roster(argv[2], "--json" in argv)
    elif cmd == "apply-roster":
        cmd_apply_roster(argv[2], argv[3] if len(argv) > 3 else None)
    elif cmd == "apply-stats":
        cmd_apply_stats(argv[2], argv[3])
    elif cmd == "effects":
        cmd_effects(argv[2])
    elif cmd == "where":
        cmd_where(argv[2], argv[3])
    elif cmd == "effect":
        cmd_effect(argv[2], argv[3:])
    elif cmd == "turn":
        cmd_turn(argv[2], argv[3:])
    elif cmd == "lastmove":
        cmd_lastmove(argv[2])
    elif cmd == "area":
        cmd_area(argv[2], argv[3:])
    elif cmd == "path":
        cmd_path(argv[2], argv[3:])
    elif cmd == "reach":
        cmd_reach(argv[2], argv[3:])
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv)
