#!/usr/bin/env python3
"""Build the combined "Table Maps" page: the battle map and the city map as two tabs of one page.

  python .claude/skills/dm-battlemap/build_combined.py [out.html]

Inputs (edit these, never the output):
  .claude/skills/dm-battlemap/battlemap.html   the battle map page (standalone)
  .claude/skills/dm-citymap/citymap.html       the city map page (standalone)

Each page keeps running as written. It is placed inside its own shadow root, so ids, styles and
`body` rules cannot collide, and its script gets a `document` stand-in that looks inside that root
(getElementById, querySelector(All), body, activeElement) and only passes key presses to the tab that
is showing. The theme colour tokens come from the battle page and are shared by both tabs.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BATTLE = os.path.join(HERE, "battlemap.html")
CITY = os.path.join(HERE, "..", "dm-citymap", "citymap.html")


def split_page(html):
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    script = re.search(r"<script>(.*)</script>\s*$", html, re.S).group(1)
    start = html.index("</style>") + len("</style>")
    body = html[start:html.rindex("<script>")]
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    return style, body.strip(), script.strip()


def top_level_blocks(css):
    """Yield (selector, block_text) for each top-level rule or at-rule, keeping order."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    i, n, out = 0, len(css), []
    while i < n:
        while i < n and css[i].isspace():
            i += 1
        if i >= n:
            break
        j = css.index("{", i)
        sel = css[i:j].strip()
        depth, k = 0, j
        while k < n:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append((sel, css[i:k + 1]))
        i = k + 1
    return out


def scope_css(css, keep_tokens):
    """Split a page's css into (token blocks, rules). Token blocks are the :root / dark-mode colour rules;
    rules have `body` rewritten to the tab's wrapper `.app`."""
    tokens, rules = [], []
    for sel, block in top_level_blocks(css):
        is_token = sel.startswith(":root") or (sel.startswith("@media (prefers-color-scheme") and ":root" in block)
        if is_token:
            tokens.append(block)
            continue
        block = re.sub(r"(^|[\s,}{])body(?=[\s.{,:])", r"\1.app", block)
        rules.append(block)
    return tokens, "\n".join(rules)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "combined.html")
    b_style, b_body, b_script = split_page(open(BATTLE, encoding="utf-8").read())
    c_style, c_body, c_script = split_page(open(CITY, encoding="utf-8").read())
    b_tokens, b_rules = scope_css(b_style, True)
    _, c_rules = scope_css(c_style, False)
    fonts = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">'

    page = f"""<title>Table Maps</title>
{fonts}
<style>
/* Shared colour tokens (from the battle map page); both tabs inherit them through their shadow roots. */
{chr(10).join(b_tokens)}
* {{ box-sizing: border-box; }}
[hidden] {{ display: none !important; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); }}
.tabs {{ display: flex; gap: 6px; padding: 10px 16px 0; max-width: 1500px; margin: 0 auto; }}
.tabs button {{ font: 600 15px var(--font-display); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); background: transparent; border: 1px solid var(--line); border-bottom: 0; border-radius: 8px 8px 0 0; padding: 8px 18px; cursor: pointer; }}
.tabs button[aria-selected="true"] {{ color: var(--ink); background: var(--panel); border-color: var(--accent); }}
.tabs button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
.tabline {{ height: 1px; background: var(--line); }}
</style>
<nav class="tabs" role="tablist" aria-label="Maps">
  <button role="tab" id="tab-battle" aria-selected="true" aria-controls="host-battle">Battle map</button>
  <button role="tab" id="tab-city" aria-selected="false" aria-controls="host-city">City map</button>
</nav>
<div class="tabline"></div>
<div id="host-battle"></div>
<div id="host-city" hidden></div>

<template id="tpl-battle"><style>
{b_rules}
</style><div class="app" id="app-battle">
{b_body}
</div></template>
<template id="tpl-city"><style>
{c_rules}
</style><div class="app" id="app-city">
{c_body}
</div></template>

<script>
(function () {{
  var REAL = document, active = "battle", apps = {{}};
  // A `document` for one tab: lookups stay inside that tab's shadow root; key presses reach only the visible tab;
  // events listened for on the document report the real inner element as their target (shadow roots retarget it).
  function makeDoc(sr, appEl, name) {{
    return new Proxy({{}}, {{
      get: function (t, p) {{
        if (p === "getElementById") return function (id) {{ return sr.getElementById(id); }};
        if (p === "querySelector") return function (s) {{ return sr.querySelector(s); }};
        if (p === "querySelectorAll") return function (s) {{ return sr.querySelectorAll(s); }};
        if (p === "body") return appEl;
        if (p === "activeElement") return sr.activeElement || {{ tagName: "" }};
        if (p === "addEventListener") return function (type, fn, opt) {{
          REAL.addEventListener(type, function (e) {{
            if ((type === "keydown" || type === "keyup") && active !== name) return;
            var proxy = new Proxy(e, {{ get: function (t2, k) {{ if (k === "target") return (e.composedPath && e.composedPath()[0]) || e.target; var v = t2[k]; return typeof v === "function" ? v.bind(t2) : v; }} }});
            return fn.call(REAL, proxy);
          }}, opt);
        }};
        var v = REAL[p]; return typeof v === "function" ? v.bind(REAL) : v;
      }},
      set: function (t, p, v) {{ REAL[p] = v; return true; }}
    }});
  }}
  function mount(name) {{
    var host = REAL.getElementById("host-" + name), sr = host.attachShadow({{ mode: "open" }});
    sr.appendChild(REAL.getElementById("tpl-" + name).content.cloneNode(true));
    apps[name] = {{ host: host, sr: sr, el: sr.getElementById("app-" + name) }};
    return makeDoc(sr, apps[name].el, name);
  }}
  var dBattle = mount("battle"), dCity = mount("city");
  function show(name) {{
    active = name;
    ["battle", "city"].forEach(function (n) {{
      apps[n].host.hidden = n !== name;
      REAL.getElementById("tab-" + n).setAttribute("aria-selected", String(n === name));
    }});
    try {{ localStorage.setItem("tm_tab", name); }} catch (e) {{}}
    try {{ history.replaceState(null, "", "#" + name); }} catch (e) {{}}
    window.dispatchEvent(new Event("resize"));            // both pages re-fit the map to the screen
  }}
  REAL.getElementById("tab-battle").onclick = function () {{ show("battle"); }};
  REAL.getElementById("tab-city").onclick = function () {{ show("city"); }};

  (function (document) {{
{b_script}
  }})(dBattle);
  (function (document) {{
{c_script}
  }})(dCity);

  var first = "battle";
  try {{ first = (location.hash || "").replace("#", "") || localStorage.getItem("tm_tab") || "battle"; }} catch (e) {{}}
  if (first !== "city") first = "battle";
  if (first === "city") show("city"); else active = "battle";
}})();
</script>
"""
    open(out_path, "w", encoding="utf-8").write(page)
    print(f"wrote {out_path} ({len(page) // 1024} KB): battle tokens {len(b_tokens)} blocks, battle rules {len(b_rules)} chars, city rules {len(c_rules)} chars")


if __name__ == "__main__":
    main()
