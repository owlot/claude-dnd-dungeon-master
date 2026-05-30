#!/usr/bin/env python3
"""
Convert a session story.md into a full session HTML page.

Usage:
    python tools/story_to_html.py <campaign> <session>

    All paths are derived from the campaign slug and session number:
      Story:  campaigns/<campaign>/party/session-N/session-N-story.md
      World:  website/<campaign>/world.html
      Output: website/<campaign>/session-N.html

    --body-only     Output only the narrative body (no page wrapper).
    --title TEXT    Campaign display title (inferred from index.html if omitted).

What this script converts:
    ## Scene Title          → <h2 id="toc-slug" data-audio="N-slug.mp3">
    [slug]: "..."           → <p class="dialogue" data-speaker="Name">
    [slug]: *"..."*         → <p class="dialogue" data-speaker="Name"><em>...</em>
    prose paragraph         → <p>...</p>
    {#anchor-slug}          → full memoir div (characters inferred from ### headings)
    ---                     → <div class="scene-break">* * *</div>
    ### Character / memoir  → skipped (parsed separately for memoir character list)

Speaker slug → display name table. Add entries here as new NPCs appear.
"""

import re
import sys
import os
import json
import argparse

def speaker_display_name(slug):
    return " ".join(w.capitalize() for w in slug.split("-"))


def slugify(title):
    """Scene title → toc slug: lowercase, spaces→hyphens, strip punctuation except hyphens."""
    s = title.lower()
    s = re.sub(r"[—–]", "-", s)       # em/en dash → hyphen
    s = re.sub(r"[^\w\s-]", "", s)    # strip punctuation
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"-+", "-", s)
    return s


def is_memoir_line(line):
    """Lines that belong to the memoir section after {#anchor}: ### Char, [anchor:...], p:, private:"""
    return (
        line.startswith("### ")
        or line.startswith("[anchor:")
        or line.startswith("p: ")
        or line.startswith("private: ")
    )


def collect_memoir_characters(path):
    """
    Scan the story for ### Character headings after {#anchor} markers.
    Returns an ordered list of character slugs (e.g. ["caelith-morn", "corrin-greenbottle", ...]).
    Order matches first appearance in the file.
    """
    chars = []
    in_memoir = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("{#"):
                in_memoir = True
                continue
            if stripped.startswith("## ") or stripped == "---":
                in_memoir = False
                continue
            if in_memoir and stripped.startswith("### "):
                name = stripped[4:].strip()
                slug = slugify(name)
                if slug not in chars:
                    chars.append(slug)
    return chars


def parse_story(path):
    """
    Parse the story.md and return a list of output tokens:
        ("scene",   scene_index, title, slug)
        ("dialogue", speaker_slug, text, italic)
        ("prose",   text)
        ("anchor",  anchor_slug)
        ("break",)
    """
    tokens = []
    scene_index = 0
    in_memoir = False
    in_memoir_character = False

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Strip frontmatter (lines 1–6: title, blank, bold metadata, in-game date, blank, ---)
    # We detect the end of frontmatter by the first ## heading.
    i = 0
    while i < len(lines) and not lines[i].startswith("## "):
        i += 1

    while i < len(lines):
        raw = lines[i].rstrip("\n")
        stripped = raw.strip()
        i += 1

        # Skip blank lines (handled by paragraph grouping below)
        if not stripped:
            continue

        # Scene heading
        if stripped.startswith("## "):
            scene_index += 1
            title = stripped[3:].strip()
            slug = slugify(title)
            tokens.append(("scene", scene_index, title, slug))
            in_memoir = False
            in_memoir_character = False
            continue

        # Horizontal rule → scene break (but skip if followed by a chapter heading)
        if stripped == "---":
            # Look ahead: if next non-blank line is a ## heading, this is a chapter
            # boundary separator, not a mid-scene audio split — don't emit a break token.
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().startswith("## "):
                in_memoir = False
                in_memoir_character = False
                continue
            tokens.append(("break",))
            in_memoir = False
            in_memoir_character = False
            continue

        # Anchor marker — prose image anchor (anchor-img-*) or memoir anchor
        if stripped.startswith("{#"):
            anchor_slug = stripped[2:-1]
            if anchor_slug.startswith("anchor-img-"):
                # Prose image anchor: renders as <p id="anchor-slug"> for postprocess injection
                tokens.append(("prose-anchor", anchor_slug))
            else:
                # Memoir anchor: switches into memoir mode
                tokens.append(("anchor", anchor_slug))
                in_memoir = True
                in_memoir_character = False
            continue

        # While in memoir mode: skip once we've entered a character block (### slug).
        # Prose between {#anchor} and the first ### is still scene prose — render it.
        if in_memoir:
            if stripped.startswith("### "):
                in_memoir_character = True
                continue
            if in_memoir_character:
                continue
            # else: scene prose before first ### — fall through to render normally

        # Tagged dialogue: [slug]: "text" or [slug]: *"text"*
        dialogue_match = re.match(r"^\[([^\]]+)\]:\s*(.*)", stripped)
        if dialogue_match:
            slug_part = dialogue_match.group(1)
            rest = dialogue_match.group(2).strip()
            # Detect italic wrapping: *"..."* or *...*
            italic = rest.startswith("*") and rest.endswith("*")
            if italic:
                rest = rest[1:-1].strip()
            tokens.append(("dialogue", slug_part, rest, italic))
            continue

        # Plain prose paragraph — collect continuation lines
        para_lines = [stripped]
        while i < len(lines):
            peek = lines[i].rstrip("\n").strip()
            if not peek:
                break
            if peek.startswith("## ") or peek.startswith("### ") or peek.startswith("{#") or peek == "---":
                break
            if re.match(r"^\[([^\]]+)\]:", peek):
                break
            if is_memoir_line(peek):
                break
            para_lines.append(peek)
            i += 1

        text = " ".join(para_lines)
        tokens.append(("prose", text))

    return tokens


def render_memoir_div(anchor_slug, session_number, memoir_chars, indent):
    """Emit the memoir anchor div for one anchor."""
    return f'{indent}<div id="{anchor_slug}" class="memoir-anchor"></div>'


PART_SUFFIXES = ["", "b", "c", "d", "e"]


def render_html(tokens, session_number, memoir_chars):
    out = []
    indent = "            "  # 12 spaces — matches existing session HTML style

    current_scene_idx = None
    current_scene_slug = None
    current_part = 0       # 0 = first part (no suffix), 1 = "b", etc.
    has_content = False    # True if we've seen prose/dialogue since the last scene or break

    for token in tokens:
        kind = token[0]

        if kind == "scene":
            _, idx, title, slug = token
            roman = to_roman(idx)
            current_scene_idx = idx
            current_scene_slug = slug
            current_part = 0
            has_content = False
            audio_slug = f"{idx:02d}-{slug}.mp3"
            out.append(f'{indent}<h2 id="toc-{slug}" data-audio="{audio_slug}">{roman}. {title}</h2>')
            out.append("")

        elif kind == "break":
            # Mid-scene break: emit data-audio pointing to the next part file
            # so audio.js can wire up a continuation play button here.
            if current_scene_slug and has_content:
                current_part += 1
                suffix = PART_SUFFIXES[current_part] if current_part < len(PART_SUFFIXES) else str(current_part)
                next_audio = f"{current_scene_idx:02d}{suffix}-{current_scene_slug}.mp3"
                out.append(f'{indent}<div class="scene-break" data-audio="{next_audio}">* * *</div>')
            else:
                out.append(f'{indent}<div class="scene-break">* * *</div>')
            has_content = False
            out.append("")

        elif kind == "prose-anchor":
            _, anchor_slug = token
            out.append(f'{indent}<p id="{anchor_slug}"></p>')
            out.append("")

        elif kind == "anchor":
            _, anchor_slug = token
            out.append(render_memoir_div(anchor_slug, session_number, memoir_chars, indent))
            out.append("")

        elif kind == "dialogue":
            _, speaker_slug, text, italic = token
            display = speaker_display_name(speaker_slug)
            content = f"<em>{text}</em>" if italic else text
            out.append(f'{indent}<p class="dialogue" data-speaker="{display}">')
            out.append(f'{indent}    {content}')
            out.append(f'{indent}</p>')
            out.append("")
            has_content = True

        elif kind == "prose":
            _, text = token
            out.append(f"{indent}<p>")
            out.append(f"{indent}    {text}")
            out.append(f"{indent}</p>")
            out.append("")
            has_content = True

    return "\n".join(out)


ROMAN = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"),  (90, "XC"),  (50, "L"),  (40, "XL"),
    (10, "X"),   (9, "IX"),   (5, "V"),   (4, "IV"), (1, "I"),
]

def to_roman(n):
    result = ""
    for value, numeral in ROMAN:
        while n >= value:
            result += numeral
            n -= value
    return result


def read_story_meta(path):
    """Extract session subtitle and campaign slug from the story frontmatter.

    Returns (subtitle, campaign_slug) — either may be None if not found.
    """
    subtitle = None
    campaign_slug = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            m = re.match(r"^# Session \d+ — (.+)$", stripped)
            if m:
                subtitle = m.group(1).strip()
                continue
            m = re.match(r"^\*\*Campaign:\*\*\s+(.+)$", stripped)
            if m:
                campaign_slug = m.group(1).strip()
                continue
            # Stop after frontmatter (first ## heading)
            if stripped.startswith("## "):
                break
    return subtitle, campaign_slug


def render_toc(tokens):
    """Return a list of (slug, display_title) for all scene tokens."""
    scenes = []
    for token in tokens:
        if token[0] == "scene":
            _, idx, title, slug = token
            roman = to_roman(idx)
            scenes.append((slug, f"{roman}. {title}"))
    return scenes


def wrap_page(body_html, session_number, subtitle, campaign_title, toc_scenes):
    """Wrap the body HTML in the full page template."""
    toc_items = "\n".join(
        f'          <li><a href="#toc-{slug}">{title}</a></li>'
        for slug, title in toc_scenes
    )
    title_tag = f"{campaign_title} — Session {session_number}: {subtitle}" if subtitle else f"{campaign_title} — Session {session_number}"
    h1 = f"{campaign_title} — Session {session_number}"
    subtitle_div = f'    <div class="chapter-subtitle">{subtitle}</div>' if subtitle else ""

    return f"""<!doctype html>
<html lang="en">
    <head>
        <meta charset="UTF-8" />
        <title>{title_tag}</title>
        <link rel="stylesheet" href="../style/story.css" />
        <script src="../js/lightbox.js" defer></script>
        <script src="../js/memoir.js?v=2" defer></script>
        <script src="../js/nav.js" defer></script>
        <script src="../js/audio.js" defer></script>
    </head>
    <body>
        <div id="lightbox" onclick="this.classList.remove('open')">
            <img id="lightbox-img" src="" alt="" />
        </div>
        <div class="container">
            <h1>{h1}</h1>
{subtitle_div}
            <nav id="chapter-toc">
                <button id="toc-toggle" title="Chapters">&#9776;</button>
                <div id="toc-panel">
                    <div class="toc-header">
                        <span class="toc-label">Chapters</span>
                        <button id="toc-close" title="Close">&#x2715;</button>
                    </div>
                    <ol>
{toc_items}
                    </ol>
                </div>
            </nav>
{body_html}
        </div>
    </body>
</html>"""


def extract_world_refs(world_html_path):
    """
    Read world.json (alongside world.html) and return {anchor_id: [display_name, ...]}
    Falls back to parsing world.html if world.json is not found.
    """
    import html as html_mod

    # Prefer world.json
    world_json_path = world_html_path.replace("world.html", "world.json")
    if os.path.exists(world_json_path):
        with open(world_json_path, encoding="utf-8") as f:
            world = json.load(f)
        refs = {}
        for section in world.get("sections", []):
            for card in section.get("cards", []):
                anchor_id = card["id"]
                name = card.get("name", "")
                if name:
                    refs.setdefault(anchor_id, [])
                    if name not in refs[anchor_id]:
                        refs[anchor_id].append(name)
        return refs

    # Fallback: parse world.html
    refs = {}
    with open(world_html_path, encoding="utf-8") as f:
        src = f.read()

    card_pattern = re.compile(
        r'<div[^>]+class="card"[^>]+id="([^"]+)"[^>]*>.*?'
        r'<span[^>]*class="card-name"[^>]*>.*?<a[^>]*>([^<]+)</a>',
        re.DOTALL,
    )
    for m in card_pattern.finditer(src):
        anchor_id = m.group(1)
        display_name = html_mod.unescape(m.group(2).strip())
        if anchor_id not in refs:
            refs[anchor_id] = []
        if display_name not in refs[anchor_id]:
            refs[anchor_id].append(display_name)

    return refs


def inject_refs(body_lines, refs_map):
    """
    Add <a class="ref"> links for first mention of each name per scene.
    refs_map: {anchor_id: [display_name, ...]}
    Returns modified lines list.
    """
    # Build flat list: (display_name, anchor_id) sorted by name length desc
    pairs = []
    for anchor_id, names in refs_map.items():
        for name in names:
            pairs.append((name, anchor_id))
    pairs.sort(key=lambda x: len(x[0]), reverse=True)

    current_scene = None
    seen = {}  # scene_slug → set of anchor_ids already linked

    result = []
    for line in body_lines:
        m = re.search(r'id="toc-([^"]+)"', line)
        if m:
            current_scene = m.group(1)
            seen.setdefault(current_scene, set())

        if current_scene and (re.search(r'>[^<]', line) or (line.strip() and not line.strip().startswith('<'))):
            for display_name, anchor_id in pairs:
                if anchor_id in seen.get(current_scene, set()):
                    continue
                pattern = r'(?<!["\w])' + re.escape(display_name) + r'(?!["\w])'
                if not re.search(pattern, line):
                    continue
                if f'href="world.html#{anchor_id}"' in line:
                    seen[current_scene].add(anchor_id)
                    continue
                parts = re.split(r'(<a\b[^>]*>.*?</a>)', line, flags=re.DOTALL)
                replaced = False
                new_parts = []
                for part in parts:
                    if replaced or part.startswith('<a'):
                        new_parts.append(part)
                        continue
                    new_part, n = re.subn(
                        r'(?<!["\w])(' + re.escape(display_name) + r')(?!["\w])',
                        f'<a class="ref" href="world.html#{anchor_id}">{display_name}</a>',
                        part,
                        count=1,
                    )
                    if n:
                        replaced = True
                    new_parts.append(new_part)
                new_line = "".join(new_parts)
                if new_line != line:
                    line = new_line
                    seen[current_scene].add(anchor_id)

        result.append(line)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Convert a session story to HTML. Derives all paths from campaign slug and session number.",
        usage="story_to_html.py <campaign> <session> [options]",
    )
    parser.add_argument("campaign", help="Campaign slug (e.g. waterdeep-dragon-heist)")
    parser.add_argument("session", type=int, help="Session number (e.g. 9)")
    parser.add_argument("--title", default=None, help="Campaign display title. Inferred from index.html if omitted.")
    parser.add_argument("--body-only", action="store_true", help="Output only the narrative body, not the full page wrapper.")
    args = parser.parse_args()

    session_number = args.session
    campaign = args.campaign

    story_path = os.path.join("campaigns", campaign, "party", f"session-{session_number}", f"session-{session_number}-story.md")
    world_path = os.path.join("website", campaign, "world.html")
    out_path = os.path.join("website", campaign, f"session-{session_number}.html")

    if not os.path.exists(story_path):
        print(f"Error: story file not found: {story_path}", file=sys.stderr)
        sys.exit(1)

    campaign_title = args.title

    tokens = parse_story(story_path)
    memoir_chars = collect_memoir_characters(story_path)
    body = render_html(tokens, session_number, memoir_chars)

    if args.body_only:
        print(body)
        return

    subtitle, campaign_slug = read_story_meta(story_path)

    # Resolve campaign display title: --title > index.html h1 > slug fallback
    if not campaign_title:
        slug_for_lookup = campaign_slug or campaign
        index_html = os.path.join("website", slug_for_lookup, "index.html")
        if os.path.exists(index_html):
            with open(index_html, encoding="utf-8") as f:
                index_src = f.read()
            m = re.search(r"<h1[^>]*>([^<]+)</h1>", index_src)
            campaign_title = m.group(1).strip() if m else slug_for_lookup
        else:
            campaign_title = slug_for_lookup

    toc_scenes = render_toc(tokens)
    page = wrap_page(body, session_number, subtitle, campaign_title, toc_scenes)

    # Inject ref links from world.html
    if os.path.exists(world_path):
        refs_map = extract_world_refs(world_path)
        lines = page.split("\n")
        lines = inject_refs(lines, refs_map)
        page = "\n".join(lines)
    else:
        print(f"WARNING: world.html not found at {world_path} — ref links skipped", file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Written: {out_path}", file=sys.stderr)

    # Re-apply image injection if a sidecar exists
    images_json_path = os.path.join("website", campaign, f"session-{session_number}-images.json")
    if os.path.exists(images_json_path):
        import subprocess, tempfile
        with open(images_json_path, encoding="utf-8") as _f:
            _sidecar = json.load(_f)
        if "anchors" in _sidecar:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            postprocess = os.path.join(script_dir, "postprocess_session.py")
            _tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            json.dump(_sidecar["anchors"], _tf, ensure_ascii=False)
            _tf.close()
            result = subprocess.run(
                [sys.executable, postprocess, out_path, "--no-backup", f"--anchors=@{_tf.name}"],
                capture_output=True, text=True,
            )
            os.unlink(_tf.name)
            if result.returncode != 0:
                print(f"WARNING: postprocess failed: {result.stderr}", file=sys.stderr)
            else:
                print(f"Images injected from {images_json_path}", file=sys.stderr)
                if result.stdout.strip():
                    print(result.stdout.strip(), file=sys.stderr)


if __name__ == "__main__":
    main()
