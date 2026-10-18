#!/usr/bin/env python3
"""Build the walking-cost grid the city map's "Find routes" uses, from the poster itself.

Usage: python3 .claude/skills/dm-citymap/src/build_routing.py [poster.jpg]

The poster is read between the city map's edges (REGION, in poster pixels) at 1/SCALE size. Every cell becomes one of
  0    blocked  (water, parkland, cliffs)
  255  wide street (light paper between the roofs, at least three cells wide)
  170  narrow lane (light paper, thinner)
  85   roofs and everything else (crossable, but slow: a route cuts through a block only when that saves a lot)
The grid is written to routing.png (next to citymap.html) and inlined into citymap.html between the ROUTE markers, which is how the
page gets it (no server needed). Rebuild when the poster changes. The map page decodes it and runs the A* search in the browser.
"""
import base64
import io
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parents[1].parent
REGION = (1965, 375, 4035, 4725)       # the city map inside the 6000 x 5200 poster
SCALE = 4


def neighbours(m, op):
    out = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            s = np.roll(np.roll(m, dy, 0), dx, 1)
            out = s if out is None else op(out, s)
    return out


def main():
    poster = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "campaigns" / "waterdeep-dragon-heist" / "sources" / "Waterdeep-map.jpg"
    x0, y0, x1, y1 = REGION
    im = Image.open(poster).convert("RGB").crop(REGION).resize(((x1 - x0) // SCALE, (y1 - y0) // SCALE), Image.BILINEAR)
    a = np.asarray(im).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    bright = (r + g + b) / 3
    water = b > r + 8
    green = (g > r + 4) & (g >= b)
    tan = (bright > 165) & (r >= b + 10) & ~water & ~green
    count = sum(np.roll(np.roll(tan.astype(int), dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    tan = count >= 5                                           # drop single-pixel specks (label halos, JPEG noise)
    wide = neighbours(tan, np.logical_and)
    grid = np.full(tan.shape, 85, np.uint8)
    grid[tan] = 170
    grid[wide] = 255
    grid[water | green] = 0
    png = io.BytesIO()
    Image.fromarray(grid, "L").save(png, "PNG", optimize=True)
    (SKILL / "routing.png").write_bytes(png.getvalue())
    (SKILL / "routing.json").write_text('{"x0": %d, "y0": %d, "s": %d, "w": %d, "h": %d}\n' % (x0, y0, SCALE, grid.shape[1], grid.shape[0]))
    b64 = base64.b64encode(png.getvalue()).decode()
    html = SKILL / "citymap.html"
    text = html.read_text(encoding="utf-8")
    block = '/*ROUTE:START*/{x0: %d, y0: %d, s: %d, png: "data:image/png;base64,%s"}/*ROUTE:END*/' % (x0, y0, SCALE, b64)
    new, n = re.subn(r"/\*ROUTE:START\*/.*?/\*ROUTE:END\*/", lambda m: block, text, flags=re.S)
    if n != 1:
        sys.exit("citymap.html has no /*ROUTE:START*/ ... /*ROUTE:END*/ placeholder")
    html.write_text(new, encoding="utf-8")
    print(f"routing grid {grid.shape[1]}x{grid.shape[0]} cells, {len(png.getvalue()) // 1024} KB png; blocked {np.mean(grid == 0):.0%}, wide {np.mean(grid == 255):.0%}, narrow {np.mean(grid == 170):.0%}, roofs {np.mean(grid == 85):.0%}")


if __name__ == "__main__":
    main()
