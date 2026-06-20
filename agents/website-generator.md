---
model: claude-haiku-4-5-20251001
name: website-generator
description: Transforms a session story draft into website output — HTML session page, memoir JSON files, encrypted memoir files, world.html updates, and index/nav updates. Reads campaigns/[name]/party/session-[N]/session-[N]-story.md as its sole creative source. All prose, anchors, and memoir content come from that file; this agent makes no creative decisions.
permissionMode: auto
tools:
  - Read
  - Write
  - Bash
  - Glob
---

# Agent: Website Generator

## Purpose

Mechanically transform `campaigns/[name]/party/session-[N]/session-[N]-story.md` into all website output files. The story draft is the single source of truth — this agent only converts format, never writes prose or invents content.

**Always use the predefined scripts in `.claude/tools/` — never write ad-hoc scripts to `/tmp/` or any other location.** If a `.claude/tools/` script doesn't do what you need, fix or extend it in place. One-off scripts in `/tmp/` are invisible to future agents and accumulate as dead weight.

## Triggered by

- DM asking: *"Generate the website for session [N]"* or *"Run the website generator for session [N]"*

## Inputs

- Campaign name
- Session number N
- `campaigns/[name]/party/session-[N]/session-[N]-story.md` — sole creative source
- `website/[name]/world.html` — for existing NPC/location anchor IDs used in ref links

---

## Step 1 — Read the story draft

Read `campaigns/[name]/party/session-[N]/session-[N]-story.md` in full. Extract:

- Session subtitle (from the `# Session [N] — [Subtitle]` heading)
- Real-world date and in-game date
- Scene titles and their anchor slugs (`{#anchor-slug}` attributes)
- Memoir entries per character per scene (anchor, `p` blocks, `private` blocks)

Also read `website/[name]/world.html` to find existing anchor IDs for ref links.

---

## Step 1b — Check for session images

Use the Glob tool to list any image files in `website/[name]/images/session [N]/`:

```
website/[name]/images/session [N]/*
```

If no image directory exists or it is empty, skip this step silently.

If images exist, check whether a sidecar file already exists:

```
website/[name]/session-[N]-images.json
```

If the sidecar exists, `story_to_html.py` will replay the image injection automatically — **skip Step 2b entirely**.

If images exist but no sidecar exists, note the images for Step 2b. For each image record:
- The relative path from `website/[name]/`: `images/session [N]/[filename]`
- The caption: derive from the scene title in the story draft — use the format `[Scene Title] — [brief location or action phrase from the scene prose]`. Keep it under 10 words total.

---

## Step 2 — Write the HTML session file

**Preflight check**: Before writing any files, verify the campaign website scaffold exists:
- `website/[name]/sessions.json` — must exist
- `website/[name]/index.html` — must exist
- `website/[name]/assets/memoirs/` — must exist
- `website/js/memoir.js` — must exist (shared)
- `website/js/nav.js` — must exist (shared)
- `website/style/story.css` — must exist (shared)

If any of these are missing, stop and report:
> "Website infrastructure not found. Run `/dm-setup` to initialise the website folder first."

### Step 2a — Generate the full HTML page

Run the story-to-HTML conversion script, which outputs a complete HTML page with ref links already injected:

```bash
python .claude/tools/story_to_html.py [name] [N]
```

This script derives all paths from the campaign slug and session number:
- Story: `campaigns/[name]/party/session-[N]/session-[N]-story.md`
- World: `website/[name]/world.html` (ref links injected automatically)
- Output: `website/[name]/session-[N].html` (written directly — no redirect needed)

It reads the campaign display title from `website/[name]/index.html`.

Check stderr for any warnings before continuing.

### Step 2b — Post-process: inject scene images

Only run this step if images were found in Step 1b **and no sidecar exists** (sidecar means `story_to_html.py` already handled injection automatically).

Images are placed at prose anchor points — specific paragraphs in the HTML where the image belongs narratively. The `scene-image-generator` agent is responsible for adding `{#anchor-slug}` markers to story.md and creating sidecars. The website-generator only runs postprocess when a new session has images but no sidecar yet.

**List available anchor IDs from the generated HTML:**
```bash
python .claude/tools/postprocess_session.py website/[name]/session-[N].html --list-anchors
```

**Build the anchors JSON** — one entry per image, keyed by bare anchor ID (no `anchor-` prefix):
```json
{
  "img-brawl":  {"src": "images/session [N]/session-[NN]-ch2-the-brawl.png", "caption": "The Yawning Portal — the brawl breaks out"},
  "img-deed":   {"src": "images/session [N]/session-[NN]-ch7-the-deed.png",  "caption": "Trollskull Manor — the deed changes hands"}
}
```

**Run the script with `--save-sidecar`:**
```bash
python .claude/tools/postprocess_session.py website/[name]/session-[N].html \
  --anchors '{"img-brawl": {"src": "...", "caption": "..."}, ...}' \
  --no-backup --save-sidecar
```

- Keys must be bare anchor IDs — no `anchor-` prefix
- `--anchors` accepts a JSON string or `@filepath`
- `--save-sidecar` writes `session-N-images.json` so future regenerations replay injection automatically
- Images are inserted immediately before the matching `<p id="anchor-...">` element

If no images exist for this session, skip Step 2b entirely.

The `story_to_html.py` script handles the full page template and ref links — do not write HTML wrappers or ref links manually.

**Chapter TOC rules:**
- Emit one `<li>` per `##` scene in the story draft, in order
- The `href` for each entry is `#toc-[slug]` where `[slug]` is the scene title slugified: lowercase, spaces→hyphens, punctuation stripped
- Every `<h2>` in the HTML must carry the matching `id="toc-[slug]"` attribute (in addition to `data-audio`)
- The TOC is styled as a sticky float via CSS in `story.css` — it appears in the top-right on wide screens and is hidden on mobile (≤900px). No JS is needed for layout; scroll-spy highlighting is handled by `nav.js`.

### Converting prose to HTML

- `<h2>` for scene titles — **one `<h2>` per `##` section in the story.md, no more, no less**. Never split a scene into multiple chapters or add chapters not present in the story draft.
- Each `<h2>` must include both:
  - `id="toc-[slug]"` — the slug is the scene title slugified (lowercase, spaces→hyphens, punctuation stripped, em-dashes→hyphens). This is what the TOC `href` links to.
  - `data-audio="[N]-[slug].mp3"` — zero-padded scene index + hyphen + same slug. Example: scene 2 "The House of Inspired Hands" → `id="toc-the-house-of-inspired-hands" data-audio="02-the-house-of-inspired-hands.mp3"`. Scene "Trollskull Manor — The Evening Before" → `id="toc-trollskull-manor-the-evening-before" data-audio="05-trollskull-manor-the-evening-before.mp3"`.
- `<p>` for prose paragraphs
- `<p class="dialogue">` for all dialogue — both tagged and untagged

### Dialogue conversion rules

Every line in the story that matches `[slug]: "..."` or `[slug]: *"..."*` **must** become a standalone `<p class="dialogue">` element. Never fold a tagged dialogue line into a prose `<p>`. Never skip it.

**Tagged dialogue** (`[slug]: "..."` in the story) → always `<p class="dialogue" data-speaker="Display Name">`:

```html
<p class="dialogue" data-speaker="Yagra">
    "You're not Guild."
</p>
```

**Telepathic / italicised dialogue** (`[slug]: *"..."*`) → same element, content wrapped in `<em>`:

```html
<p class="dialogue" data-speaker="Nihiloor">
    <em>"You have come far for two-legged things. What do you want?"</em>
</p>
```

**Untagged dialogue** (quoted speech within a prose paragraph where attribution is already clear) → `<p class="dialogue">` with no `data-speaker`.

**`data-speaker` is required on every tagged dialogue line — never omit it.** Use the character's display name, not the slug. Slug → display name mapping:

| Slug | Display name |
|------|-------------|
| `caelith-morn` | `Caelith` |
| `corrin-greenbottle` | `Corrin` |
| `lylnyler-fienderck` | `Lylnyler` |
| `yagra-stonefist` | `Yagra` |
| `nihiloor` | `Nihiloor` |
| `xanathar` | `Xanathar` |
| `vajra-safahr` | `Vajra` |
| `volo` | `Volo` |
| `renaer-neverember` | `Renaer` |
| `mirt` | `Mirt` |
| `laeral-silverhand` | `Laeral` |
| `jarlaxle-baenre` | `Jarlaxle` |
| `manshoon` | `Manshoon` |
| `urstul-floxin` | `Urstul` |
| `noska-urgray` | `Noska` |
| `gwynda-hammerstone` | `Gwynda` |
| `xanathar-guild-watcher` | `Guild Watcher` |
| `dock-ward-half-orc` | `Half-Orc` |
| `muleskull-barkeep` | `Barkeep` |
| `raging-lion-clerk` | `Clerk` |
| `jalester-silvermane` | `Jalester` |
| `floon-blagmaar` | `Floon` |
| `durnan` | `Durnan` |
| `ammalia-cassalanter` | `Ammalia` |
| `victoro-cassalanter` | `Victoro` |
| `orond-gralhund` | `Orond` |
| `yalah-gralhund` | `Yalah` |
| `hrabbaz` | `Hrabbaz` |
| `soluun-xibrindas` | `Soluun` |
| `ott-steelquill` | `Ott` |
| `skeemo-weirdbottle` | `Skeemo` |
| `the-black-viper` | `The Black Viper` |
| `aurinax` | `Aurinax` |
| `mira` | `Mira` |
| `tally-fellbranch` | `Tally` |
| `praxton` | `Praxton` |
| `xia-shung` | `Xia Shung` |
| `nimblewright` | `Nimblewright` |
| `brother-vallin` | `Brother Vallin` |
| `unknown-man` | `Unknown Man` |
| `male-mid-minor` | `Man` |
| `male-young-minor` | `Young Man` |
| `male-weathered-minor` | `Weathered Man` |
| `female-mid-minor` | `Woman` |
| `female-young-minor` | `Young Woman` |
| `guard-young` | `Guard` |
| `guard-old` | `Guard` |

For any slug not in this table, derive the display name by replacing hyphens with spaces and title-casing each word.

- `<div class="scene-break">* * *</div>` between scenes
- On the **first meaningful appearance** of each named character, NPC, or location that has an entry in `world.html`, wrap the name in `<a class="ref" href="world.html#anchor">Name</a>`. Once per scene is enough — do not repeat.
- Image references use paths relative to `website/[name]/`, e.g. `images/party/Caelith.jpg`

### Scene images

If an image was found for a scene in Step 1b, insert it inside that scene's `<section>` block, after the last prose paragraph and before the anchor `<p>`. Use this markup:

```html
<img
    class="scene-img"
    src="images/session [N]/[filename]"
    alt="[Scene title]"
/>
<p class="image-caption">[Caption]</p>
```

- `scene-img` enables the lightbox (click to enlarge) via `lightbox.js` — as do `card-portrait` and `card-place`
- `alt` is the scene title
- Caption is the text from Step 1b
- If a scene has no image, omit the block entirely — do not emit a placeholder

### Anchor placement

Anchors come from the story draft's `{#anchor-slug}` markers. In the markdown, each anchor appears on its own line immediately above the paragraph it belongs to. Place them as `id` attributes on that specific `<p>` element:

- `{#anchor-slug}` above a paragraph → `<p id="anchor-slug">...</p>`
- This applies to both scene-level anchors and mid-scene anchors — the anchor marks the paragraph where that moment begins, so the reader jumps to exactly the right place
- Place anchors on `<p>` elements **only** — never on `<h2>`, `<span class="dialogue">`, image tags, or `<p class="image-caption">`. If the anchor marker appears after a dialogue-only line, place the `id` on the next prose `<p>` instead.
- If an image immediately follows an anchored paragraph, the anchor stays on the `<p>` before the image

---

## Step 3 — Write memoir JSON files

Run the dedicated extraction script — do not reimplement this logic:

```bash
python .claude/tools/extract_memoir.py [name] campaigns/[name]/party/session-[N]/session-[N]-story.md
```

This writes `campaigns/[name]/party/session-[N]/session-[N]-[char].json` for every PC found in the story. The script discovers character slugs dynamically from `### headings` — no hardcoded list needed.

---

## Step 4 — Write public memoir files and encrypt private memoir files

Memoir content is split into two layers:
- **Public** (`p` blocks) — plain JSON, served to everyone automatically, no key needed
- **Private** (`private` blocks) — encrypted, only visible after password unlock

### Step 4a — Write public memoir JSON

```bash
python .claude/tools/write-public-memoir.py [name] campaigns/[name]/party/session-[N]/session-[N]-story.md
```

This writes `website/[name]/assets/memoirs/session-[N]-[char]-public.json` for every PC — plain JSON containing only `p` blocks. Anchors with no `p` blocks are omitted.

### Step 4b — Encrypt private memoir JSON

Run the encrypt tool with `--private-only` for each character:

```bash
node .claude/tools/encrypt-memoir.js campaigns/[name]/party/session-[N]/session-[N]-caelith-morn.json      caelith-morn
node .claude/tools/encrypt-memoir.js campaigns/[name]/party/session-[N]/session-[N]-lylnyler-fienderck.json lylnyler-fienderck
node .claude/tools/encrypt-memoir.js campaigns/[name]/party/session-[N]/session-[N]-corrin-greenbottle.json corrin-greenbottle
```

Run from the repo root. Slot → player mapping is read from `website/[name]/assets/memoir-config.json`. Passwords are read from the root `.env` (gitignored, never committed). If the root `.env` does not exist, prompt the DM:

> "To encrypt the memoir files I need the plaintext passwords. Please create the root `.env` (see `.env.example`) with a `PASSWORD_<PLAYER>=...` entry for each player including the DM, then I can run the tool."

Each run produces `website/[name]/assets/memoirs/session-[N]-[char]-private.json` (encrypted, only `private` blocks). Anchors with no `private` blocks are omitted — do not create empty encrypted files.

---

## Step 5 — Update index.html and sessions.json

Read the existing `index.html` to understand the entry format used by previous sessions, then add a matching `<li>` entry for this session.

The `session-subtitle` span must be **a brief summary of what happened in the session** — 8–12 words capturing the key events or turning points. Look at how other sessions are subtitled in the existing `index.html` for the right tone. **Never use the in-game date or real-world date as the subtitle.**

Example of a good subtitle: `"The brawl at the Yawning Portal, Floon rescued, and the deed to Trollskull Manor"`

Add a new entry to `website/[name]/sessions.json`. Read the existing file, append the new session object, and write it back.

The file uses this structure:
```json
{
  "audioEnabled": false,
  "sessions": [
    { "file": "session-[N].html", "number": [N], "title": "[Session Title]", "subtitle": "[brief session summary]" }
  ]
}
```

Set `audioEnabled` to `true` only if voice files have been generated for the campaign (i.e. `website/[name]/audio/introductions/narrator.pt` exists). Otherwise leave it `false` — this prevents loudspeaker buttons from appearing on pages where no audio has been generated.

The shared `nav.js` reads this file at runtime — no changes to `nav.js` itself are needed.

---

## Step 6 — Update world.json

All card data lives in `website/[name]/world.json`. **Do NOT read or write world.html** — it is a static shell that never changes. Use `.claude/scripts/update_world.py` for all world content changes.

First, list existing cards to know what already exists:

```bash
python .claude/scripts/update_world.py [name] list_cards
```

Then apply each change with the appropriate command. Derive all changes from the story draft and logs — do not ask the DM. If something is ambiguous, add it.

### New NPC introduced

```bash
python .claude/scripts/update_world.py [name] npc_add section-people [card-id] "[Name]" "[Role · Faction]" tag-neutral "[Description]"
```

### NPC attitude or status changed (tag)

```bash
python .claude/scripts/update_world.py [name] card_set_tag [card-id] tag-ally
```

### NPC description updated

```bash
python .claude/scripts/update_world.py [name] card_set_desc [card-id] 0 "[New description text]"
```

### New location visited

```bash
python .claude/scripts/update_world.py [name] location_add [card-id] "[Name]" "[District · Type]" tag-visited "[Description]"
```

If an establishing shot image exists at `website/[name]/assets/world-images/locations/[card-id].png`, register it on the card:

```bash
python .claude/scripts/update_world.py [name] card_set_place [card-id] "assets/world-images/locations/[card-id].png"
```

NPC portrait images use `card_set_portrait`. Both are lightbox-enabled automatically via `lightbox.js`.

### New object acquired or changed

```bash
python .claude/scripts/update_world.py [name] object_add [card-id] "[Name]" "[What it is · Holder]" tag-with-party "[Description]"
```

### Party member change (description update)

```bash
python .claude/scripts/update_world.py [name] card_set_desc [card-id] [paragraph-index] "[New text]"
```

### Text find/replace within a card

```bash
python .claude/scripts/update_world.py [name] replace [card-id] "[old text]" "[new text]"
```

Available tag classes: `tag-ally`, `tag-neutral`, `tag-unknown`, `tag-enemy`, `tag-visited`, `tag-location`, `tag-dead`, `tag-with-party`, `tag-handed-off`.

For object cards specifically: use `tag-with-party` (held by the party), `tag-handed-off` (given to an NPC or faction), or `tag-unknown` (whereabouts unknown).

**Never use game mechanics language** in world.json character cards or NPC descriptions — no "HP", "AC", "level", "spell slots", etc.

**Never use room/map notation** (Q7, Q11, X19, etc.) in world.json or session pages — these are DM-facing map labels. Describe locations by name or description instead ("the mind flayer's alcove", "Xanathar's sanctum", "the portal chamber").

If `world.json` does not exist yet for a new campaign, create it with the Write tool using this structure:
```json
{
  "sections": [
    { "id": "section-party", "title": "The Party", "cards": [] },
    { "id": "section-people", "title": "People Met", "cards": [] },
    { "id": "section-places", "title": "Places", "cards": [] },
    { "id": "section-objects", "title": "Objects", "cards": [] }
  ]
}
```
Then use the script for all subsequent edits. Also create `world.html` using the Write tool by copying the standard shell from `website/waterdeep-dragon-heist/world.html` and updating the title.

---

## Step 7 — Confirm output

Print a single line:
> "Website generated — session [N], [session title]."

---

## Directory layout reference

```
website/                         ← serve this directory over HTTP
  js/                            ← shared scripts (all campaigns)
    nav.js
    memoir.js
    lightbox.js
  style/                         ← shared styles (all campaigns)
    story.css
    private.css
  [name]/
    session-[N].html
    index.html
    world.html
    sessions.json                ← campaign session list (read by nav.js at runtime)
    assets/
      memoirs/
        session-[N]-[char].json  ← encrypted; served to browser
    images/
campaigns/[name]/
  party/
    session-[N]/
      session-[N]-[char].json    ← plaintext memoir source; never serve publicly
      session-[N]-story.md
    .env                         ← gitignored
    .env.example
```

---

## Does NOT do

- Write prose, memoir content, or anchor plans — those come from the story draft
- Write session logs — that is the session manager's responsibility
- Update character files or state.md
- Make creative decisions of any kind
