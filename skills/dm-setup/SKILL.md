---
description: First-time setup and add-campaign — creates shared website infrastructure on first run, then walks through setting up a campaign folder. Deploys CLAUDE.md, .gitignore, and JS/CSS from templates. Safe to run multiple times.
argument-hint: ""
---

# DM Setup

This skill is safe to run multiple times. It checks what already exists and only creates what is missing — it never overwrites existing files.

Two modes:
- **First run**: `website/` doesn't exist yet — creates shared infrastructure + first campaign
- **Add campaign**: `website/` already exists — skips infrastructure, sets up another campaign

Walk through the steps below **one at a time**, waiting for an answer before proceeding.

---

## Step 1 — Welcome and detect mode

Greet the user briefly. Check whether `website/index.html` exists:

- **Does not exist** → first run. Say: *"Let's get you set up. I'll create the shared website infrastructure and your first campaign."*
- **Exists** → adding a campaign. Say: *"Website infrastructure already exists. Let's add a new campaign."*

Set `FIRST_RUN = true/false` accordingly.

State the absolute path of `PROJECT_ROOT` — the directory containing `CLAUDE.md`. Every file operation uses this path as the base.

---

## Step 2 — Campaign name

Ask:
> "What's the name of your campaign? This becomes the folder slug — e.g. `curse-of-strahd`, `waterdeep-dragon-heist`, `my-homebrew`. Lowercase with hyphens, no spaces."

Slugify their answer: lowercase, spaces → hyphens, strip special characters. Confirm the slug before continuing.

**If `campaigns/[slug]/party/state.md` already exists**: warn the user and ask whether to continue. Do not overwrite an existing campaign — stop here if they say no.

Set `CAMPAIGN` = the confirmed slug.
Set `CAMPAIGN_DISPLAY` = a title-cased display name (e.g. `My Homebrew`).

---

## Step 3 — Website

Ask:
> "Would you like to set up the session story website for this campaign? It publishes illustrated, audio-narrated session recaps that players can read between sessions. (You can add it later if you skip now.)"

- **Yes** → continue to Step 4.
- **No / later** → skip to Step 6, mark `WEBSITE=false`.

---

## Step 4 — Players (website only)

**If FIRST_RUN**: collect the full player roster — these go into `website/assets/config.json` which is shared across all campaigns.

**If not FIRST_RUN**: read `website/assets/config.json`. Tell the DM the existing player list and ask:
> "These players are already registered: [list]. Do you want to add any new players for this campaign, or use the existing list?"

If adding players: collect their usernames and ask for passwords (or set placeholder hashes).

Either way, confirm the DM username and collect the character roster for this campaign (character slug, display name, player username, color).

Collect (or confirm):
- `dm`: DM's username slug
- `players`: all usernames (existing + any new ones)
- Per character: `slug` (kebab-case name), `player` (username), `name` (display name), `color`

---

## Step 5 — TTS backend (website, first run only)

**Skip this step if not FIRST_RUN** — `ttsBackend` is already set in `website/assets/config.json`.

Ask:
> "Do you want audio narration for session recaps? If so, which TTS backend — `moss` or `qwen3` (default)? You can change this later in `website/assets/config.json`."

- **Yes** → set `TTS_BACKEND` to their choice.
- **No / later** → set `TTS_BACKEND` to `qwen3`.

Mark `WEBSITE=true`.

---

## Step 6 — Create shared website infrastructure (first run only)

**Skip this entire step if not FIRST_RUN.**

Create directories:

```
website/
  js/
  style/
  assets/
  audio/
```

Copy `templates/CLAUDE.md` → `CLAUDE.md` at the project root. Always overwrite — this file is framework infrastructure, not user content.

Copy `templates/gitignore.template` → `.gitignore` at the project root. Always overwrite — this file is framework infrastructure.

Then copy each file from `.claude/skills/dm-setup/templates/` to `website/` using `Bash(cp ...)`. Always copy — overwrite any existing version so the installed files match the templates:
- `templates/js/audio.js` → `website/js/audio.js`
- `templates/js/lightbox.js` → `website/js/lightbox.js`
- `templates/js/memoir.js` → `website/js/memoir.js`
- `templates/js/nav.js` → `website/js/nav.js`
- `templates/js/world.js` → `website/js/world.js`
- `templates/style/story.css` → `website/style/story.css`
- `templates/style/private.css` → `website/style/private.css`
- `templates/index.html` → `website/index.html` (only if it does not already exist — this file contains the campaign list and must not be overwritten)

Write `website/assets/config.json`:

```json
{
  "ttsBackend": "[TTS_BACKEND]",
  "players": {
    "[username]": {
      "hash": "[sha256-of-password]"
    }
  }
}
```

For password hashes — ask the DM now or later:
- **Now**: compute SHA-256 per player: `Bash(node -e "const c=require('crypto'); console.log(c.createHash('sha256').update('[password]'.toLowerCase().trim()).digest('hex'))")`
- **Later**: use `"[set-hash-here]"` as placeholder. Login will not work until hashes are set.

The `website/audio/` folder holds shared audio assets (narrator voice, introductions); create it empty.

---

## Step 6b — Update config for new players (add-campaign only, if new players were added)

**Only if not FIRST_RUN and new players were added in Step 4.**

Read `website/assets/config.json`, merge the new player entries in, and write it back. Never remove existing players.

---

## Step 7 — Create campaign folder structure

Create using `Bash(mkdir -p ...)` — `mkdir -p` is safe to run on existing directories:

```
campaigns/[CAMPAIGN]/
  party/
    characters/
    session-1/
  info/
    encounters/
    npcs/
    locations/
  sources/
```

For each file below, **only write it if it does not already exist**:

`campaigns/[CAMPAIGN]/party/state.md`:
```markdown
# Campaign State — [CAMPAIGN_DISPLAY]

**Session**: 0
**In-game date**:
**Location**:
**Last updated**: [today's date]

---

## Last Session Summary

## Party

## Active Quests

## Open Threads

## Next Session Prep Notes

## Factions
```

`campaigns/[CAMPAIGN]/party/session-log.md`:
```markdown
# Session Log — [CAMPAIGN_DISPLAY]

---
```

`campaigns/[CAMPAIGN]/party/relationships.md`:
```markdown
# NPC Relationships — [CAMPAIGN_DISPLAY]

| NPC | Disposition | Notes |
|-----|-------------|-------|
```

`campaigns/[CAMPAIGN]/party/voice-overrides.json`:
```json
{}
```

`campaigns/[CAMPAIGN]/party/phonetic-substitutions.json`:
```json
{}
```

Note: `tts-backend` is **not** written to the campaign folder. The TTS backend is configured in `website/assets/config.json` and applies to all campaigns on this site.

---

## Step 8 — Create campaign website folder (if WEBSITE=true)

Create using `mkdir -p` — safe on existing directories:

```
website/[CAMPAIGN]/
  audio/
    introductions/
  images/
  assets/
    memoirs/
    world-images/
      characters/
      locations/
      npcs/
      objects/
```

For each file below, **only write it if it does not already exist**:

`website/[CAMPAIGN]/sessions.json`:
```json
{
  "audioEnabled": false,
  "sessions": []
}
```

`website/[CAMPAIGN]/assets/memoir-config.json`:
```json
{
  "dm": "[dm-slug]",
  "characters": {
    "[character-slug]": {
      "player": "[player-slug]",
      "name": "[Character Display Name]",
      "color": "[color]",
      "portrait": "assets/world-images/characters/[CharacterName]/portrait.png"
    }
  }
}
```

`website/[CAMPAIGN]/world.json`:
```json
{
  "locations": [],
  "npcs": [],
  "factions": []
}
```

`website/[CAMPAIGN]/index.html`: read `.claude/skills/dm-setup/templates/campaign-index.html`, replace `{{CAMPAIGN_DISPLAY}}` and `{{CAMPAIGN}}`, write to `website/[CAMPAIGN]/index.html`.

`website/[CAMPAIGN]/world.html`: read `.claude/skills/dm-setup/templates/campaign-world.html`, replace `{{CAMPAIGN_DISPLAY}}` and `{{CAMPAIGN}}`, write to `website/[CAMPAIGN]/world.html`.

Then update `website/index.html`: read the file, find `<ul class="campaign-list">`, and insert a new `<li>` **only if a link to `[CAMPAIGN]/index.html` is not already present**:
```html
<li>
    <a href="[CAMPAIGN]/index.html">
        <span class="campaign-name">[CAMPAIGN_DISPLAY]</span>
        <span class="campaign-meta">D&amp;D 5e · 0 sessions</span>
    </a>
</li>
```

---

## Step 9 — Summary and next steps

Print a clear summary of what was created vs skipped:

```
✓ Campaign folder: campaigns/[CAMPAIGN]/
✓ State file: campaigns/[CAMPAIGN]/party/state.md  [or: already existed — skipped]
[✓ Website infrastructure: website/]               [or: already existed — skipped]
[✓ Campaign website: website/[CAMPAIGN]/]
[✓ Site config: website/assets/config.json]
[⚠ Player password hashes are placeholders — update website/assets/config.json before sharing the site]

Next steps:
1. Run /dm-create-characters [CAMPAIGN] to set up your player characters
2. If you have source material, place it in campaigns/[CAMPAIGN]/sources/ and run
   /dm-index-campaign [CAMPAIGN] — or run /dm-generate-campaign [CAMPAIGN] to
   build a campaign from scratch
3. When ready → /dm-start-session [CAMPAIGN]
```
