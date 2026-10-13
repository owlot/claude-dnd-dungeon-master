#!/usr/bin/env python3
"""
Cache-bust the site's JS and CSS: give every <script src> / <link href> that
points at js/NAME.js or style/NAME.css a version query (?v=<content hash>).

The hash is taken from the file's content, so the version changes exactly when
the file changes and browsers refetch it instead of using a stale cached copy.

    python .claude/scripts/bump_asset_versions.py            # rewrite HTML in place
    python .claude/scripts/bump_asset_versions.py --check    # exit 1 if any tag is stale
    python .claude/scripts/bump_asset_versions.py --hook     # for a Claude Code PostToolUse hook:
                                                             # reads the tool-call JSON on stdin and
                                                             # runs only if a js/ or style/ file changed

HTML files updated:
  - website/**/*.html (hash of website/js, website/style)
  - .claude/skills/dm-setup/templates/*.html (hash of templates/js, templates/style)
Generators that write HTML (story_to_html.py) import version() from here, so
new pages are born with the right version.
"""

import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SITE = os.path.join(ROOT, "website")
TEMPLATES = os.path.join(ROOT, ".claude", "skills", "dm-setup", "templates")

TAG = re.compile(r'((?:src|href)=")((?:\.\./)?(?:js|style)/([\w.-]+\.(?:js|css)))(?:\?v=[^"]*)?(")')


def version(name, base=SITE):
    """Short content hash of base/js/<name> or base/style/<name>."""
    sub = "js" if name.endswith(".js") else "style"
    path = os.path.join(base, sub, name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:8]


def rewrite(html_path, base):
    with open(html_path, encoding="utf-8") as f:
        text = f.read()

    def sub(m):
        v = version(m.group(3), base)
        if v is None:
            return m.group(0)
        return f'{m.group(1)}{m.group(2)}?v={v}{m.group(4)}'

    new = TAG.sub(sub, text)
    return text, new


def run(check=False):
    targets = [(p, SITE) for p in glob.glob(os.path.join(SITE, "**", "*.html"), recursive=True)]
    targets += [(p, TEMPLATES) for p in glob.glob(os.path.join(TEMPLATES, "*.html"))]
    stale = 0
    for path, base in sorted(targets):
        old, new = rewrite(path, base)
        if old != new:
            stale += 1
            if not check:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new)
    return stale


def main():
    if "--hook" in sys.argv:
        try:
            data = json.load(sys.stdin)
        except Exception:
            return
        path = (data.get("tool_input") or {}).get("file_path", "")
        if not re.search(r"/(website|templates)/(js|style)/[\w.-]+\.(js|css)$", path):
            return
        n = run()
        if n:
            print(f"bump_asset_versions: updated {n} HTML file(s) after {os.path.basename(path)} changed")
        return
    check = "--check" in sys.argv
    n = run(check=check)
    if check:
        print(f"{n} HTML file(s) have stale asset versions")
        sys.exit(1 if n else 0)
    print(f"Updated {n} HTML file(s)")


if __name__ == "__main__":
    main()
