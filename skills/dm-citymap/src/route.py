#!/usr/bin/env python3
"""Walking routes on the city map, for the DM assistant (standard library only). Python twin of the A* in citymap.html:
the same routing.png grid (see build_routing.py), the same costs, penalty-based alternatives and 3 mph walking time.

  python3 .claude/skills/dm-citymap/src/route.py "Trollskull Manor" "Yawning Portal"
  python3 .claude/skills/dm-citymap/src/route.py 3407,1327 C48

A point is "x,y" in poster pixels, a pin label, or a building from the printed legend (code such as C48 or a name). Pins are read from the
table chat's map database through table_chat.py (map-route / map-routes); run on its own this file knows only legend buildings and x,y.
"""
import heapq
import json
import re
import struct
import sys
import zlib
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FT_PER_PX = 1000 / 189.5
_GRID = {}


def _read_png_gray(path):
    """8-bit grayscale PNG -> (w, h, bytes). Enough for routing.png, which Pillow writes in that format."""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, hdr = 8, b"", None
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat += body
    w, h, depth, ctype, _, _, interlace = hdr
    if depth != 8 or ctype != 0 or interlace:
        raise ValueError("routing.png must be an 8-bit grayscale PNG without interlacing")
    raw = zlib.decompress(idat)
    out = bytearray(w * h)
    prev = bytearray(w)
    for y in range(h):
        f = raw[y * (w + 1)]
        line = bytearray(raw[y * (w + 1) + 1:(y + 1) * (w + 1)])
        if f == 1:
            for x in range(1, w):
                line[x] = (line[x] + line[x - 1]) & 255
        elif f == 2:
            for x in range(w):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(w):
                line[x] = (line[x] + (((line[x - 1] if x else 0) + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(w):
                a = line[x - 1] if x else 0
                b = prev[x]
                c = prev[x - 1] if x else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out[y * w:(y + 1) * w] = line
        prev = line
    return w, h, out


def grid():
    if not _GRID:
        meta = json.loads((SKILL / "routing.json").read_text())
        w, h, px = _read_png_gray(SKILL / "routing.png")
        inf = float("inf")
        _GRID.update(meta, w=w, h=h, cost=[inf if v == 0 else 1.0 if v >= 240 else 1.6 if v >= 150 else 5.0 for v in px])
    return _GRID


def _snap(g, px, py):
    cx, cy = int((px - g["x0"]) // g["s"]), int((py - g["y0"]) // g["s"])
    w, h, cost = g["w"], g["h"], g["cost"]
    if cx < 0 or cy < 0 or cx >= w or cy >= h:
        return -1
    best, bd, anyc, ad = -1, 1e9, -1, 1e9
    for r in range(41):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                x, y = cx + dx, cy + dy
                if x < 0 or y < 0 or x >= w or y >= h:
                    continue
                c = cost[y * w + x]
                if c == float("inf"):
                    continue
                d = dx * dx + dy * dy
                if c <= 1.6 and d < bd:
                    bd, best = d, y * w + x
                if d < ad:
                    ad, anyc = d, y * w + x
        if best >= 0 and r > 0 and bd <= r * r:
            break
        if r >= 20 and best < 0 and anyc >= 0:
            break
    return best if best >= 0 else anyc


_NB = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (-1, -1, 1.4142)]


def _astar(g, s, t, extra):
    w, h, cost = g["w"], g["h"], g["cost"]
    tx, ty = t % w, t // w
    inf = float("inf")
    dist = {s: 0.0}
    prev = {}
    done = set()
    heap = [(0.0, s)]

    def hh(i):
        dx, dy = abs(i % w - tx), abs(i // w - ty)
        return dx + dy - 0.5858 * min(dx, dy)
    while heap:
        _, cur = heapq.heappop(heap)
        if cur in done:
            continue
        done.add(cur)
        if cur == t:
            break
        x, y, gc = cur % w, cur // w, dist[cur]
        for dx, dy, step in _NB:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            ni = ny * w + nx
            c = cost[ni]
            if c == inf or ni in done:
                continue
            ng = gc + step * (cost[cur] + c) / 2 * (extra.get(ni, 1.0) if extra else 1.0)
            if ng < dist.get(ni, inf):
                dist[ni] = ng
                prev[ni] = cur
                heapq.heappush(heap, (ng + hh(ni), ni))
    if t not in dist:
        return None
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    return path[::-1]


def _simplify(pts, eps):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop()
        ax, ay = pts[i0]
        bx, by = pts[i1]
        dx, dy = bx - ax, by - ay
        ln = (dx * dx + dy * dy) ** 0.5 or 1
        md, mi = 0, -1
        for i in range(i0 + 1, i1):
            d = abs(dy * (pts[i][0] - ax) - dx * (pts[i][1] - ay)) / ln
            if d > md:
                md, mi = d, i
        if md > eps:
            keep[mi] = True
            stack += [(i0, mi), (mi, i1)]
    return [p for p, k in zip(pts, keep) if k]


def feet(pts):
    return sum(((pts[i][0] - pts[i + 1][0]) ** 2 + (pts[i][1] - pts[i + 1][1]) ** 2) ** 0.5 for i in range(len(pts) - 1)) * FT_PER_PX


def fmt_ft(ft):
    r = round(ft / 10) * 10
    return f"{r:,} ft" + (f" ({ft / 5280:.2f} mi)" if ft >= 1000 else "")


def fmt_time(ft):
    m = ft / 264                                                # 3 miles an hour = 264 ft a minute
    if m < 1:
        return "under a minute"
    if m < 90:
        return f"about {round(m)} min"
    hrs, rest = int(m // 60), round((m - (m // 60) * 60) / 5) * 5
    if rest == 60:
        hrs, rest = hrs + 1, 0
    return f"about {hrs} h" + (f" {rest} min" if rest else "")


def find_routes(a, b):
    """a, b: (x, y) in poster pixels. Returns {'options': [{'ft', 'pts'}...]} (shortest first) or {'error': text}."""
    g = grid()
    s, t = _snap(g, *a), _snap(g, *b)
    if s < 0 or t < 0:
        return {"error": "Both points must be on the city map itself (not the ward lists or the margins)."}
    w, rad, mult, extra, found = g["w"], 6, 4.0, {}, []
    for attempt in range(7):
        if len(found) >= 3:
            break
        path = _astar(g, s, t, extra if attempt else None)
        if not path:
            if found:
                break
            return {"error": "No way through between those two spots (water or parkland in the way)."}
        shared = sum(1 for i in path if extra.get(i, 1.0) > 1) if found else 0
        if not found or shared / len(path) < 0.75:
            found.append(path)
        for i in path:
            cx, cy = i % w, i // w
            for y in range(max(0, cy - rad), min(g["h"] - 1, cy + rad) + 1):
                for x in range(max(0, cx - rad), min(w - 1, cx + rad) + 1):
                    k = y * w + x
                    if extra.get(k, 1.0) < mult:
                        extra[k] = mult
        if attempt >= 2:
            rad, mult = rad + 2, mult + 1.5
    options = []
    for path in found:
        cells = [(g["x0"] + (i % w + .5) * g["s"], g["y0"] + (i // w + .5) * g["s"]) for i in path]
        eps = g["s"] * .6
        sp = _simplify(cells, eps)
        while len(sp) > 36:
            eps *= 1.5
            sp = _simplify(cells, eps)
        pts = [tuple(a)] + [(round(x), round(y)) for x, y in sp] + [tuple(b)]
        options.append({"ft": feet(pts), "pts": pts})
    options.sort(key=lambda o: o["ft"])
    return {"options": options}


# ------------------------------------------------------------------------------------------------ naming points
def _legend():
    try:
        return json.loads((SKILL / "legend.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def resolve(spec, pins=()):
    """-> (label, x, y) or raises ValueError with what to do. pins: [{'label', 'x', 'y'}]."""
    spec = spec.strip()
    m = re.fullmatch(r"(\d+)\s*[, ]\s*(\d+)", spec)
    if m:
        return (f"({m.group(1)}, {m.group(2)})", int(m.group(1)), int(m.group(2)))
    low = spec.lower()
    cands = [(p["label"], p["x"], p["y"]) for p in pins if p["label"].lower() == low] or [(p["label"], p["x"], p["y"]) for p in pins if low in p["label"].lower()]
    if not cands:
        leg = [e for e in _legend() if e.get("pos")]
        cands = [(f"{e['name']} ({e['code']})", e["pos"][0], e["pos"][1]) for e in leg if e["code"].lower() == low] or \
                [(f"{e['name']} ({e['code']})", e["pos"][0], e["pos"][1]) for e in leg if e["name"].lower() == low] or \
                [(f"{e['name']} ({e['code']})", e["pos"][0], e["pos"][1]) for e in leg if low in e["name"].lower()]
    if not cands:
        raise ValueError(f'"{spec}" is not a pin, a building in the printed legend, or an x,y point.')
    if len({(c[1], c[2]) for c in cands}) > 1:
        raise ValueError(f'"{spec}" matches several places: ' + "; ".join(c[0] for c in cands[:8]) + ". Use a more exact name, a legend code like C48, or x,y.")
    return cands[0]


def saved_summary(routes):
    out = []
    for r in routes:
        ft = feet([(q["x"], q["y"]) for q in r["pts"]])
        a, b = r["pts"][0].get("l") or "a point", r["pts"][-1].get("l") or "a point"
        out.append({"name": r["name"], "from": a, "to": b, "ft": ft, "by": r.get("owner") or "DM", "pub": bool(r.get("pub")), "pins": (r["pts"][0].get("p"), r["pts"][-1].get("p"))})
    return out


def describe(a, b, options, saved=()):
    lines = [f"{a[0]} to {b[0]}: straight line {fmt_ft(((a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5 * FT_PER_PX)}."]
    for r in saved:
        lines.append(f'Saved route "{r["name"]}" ({r["from"]} to {r["to"]}, by {r["by"]}): {fmt_ft(r["ft"])}, {fmt_time(r["ft"])} on foot.')
    lines.append("Computed walking routes (3 mph, along the streets of the poster; narrow alleys are approximate):")
    for i, o in enumerate(options):
        lines.append(f"  {'Shortest' if i == 0 else 'Alternative ' + str(i)}: {fmt_ft(o['ft'])}, {fmt_time(o['ft'])}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    try:
        pa, pb = resolve(sys.argv[1]), resolve(sys.argv[2])
    except ValueError as exc:
        sys.exit(str(exc))
    res = find_routes(pa[1:], pb[1:])
    print(res["error"] if "error" in res else describe(pa, pb, res["options"]))
