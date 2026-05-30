---
description: Generate audio MP3s for a session — scene chapters and per-anchor memoir files. Requires locked voice files and a session story file. Run after the website-generator has produced the session HTML and memoir JSONs.
argument-hint: "[campaign-slug] [session-number] — e.g. 'waterdeep-dragon-heist 7'"
---

Generate audio for session: $ARGUMENTS

## Overview

This skill:
1. Validates that voice files and story/memoir files are in place
2. Copies any updated files to where the generator can find them
3. Runs `.claude/tools/generate-audio.py` for scenes and memoirs
4. Copies the generated MP3s to `website/[campaign]/audio/session-N/`
5. Confirms what was produced

**Project root:** use the absolute project root for all paths and commands.

---

## Step 1 — Parse arguments

Split `$ARGUMENTS` into:
- `CAMPAIGN` = first word (e.g. `waterdeep-dragon-heist`)
- `SESSION` = second word — session number, e.g. `7` → `session-7`

If either is missing, ask the DM.

---

## Step 2 — Preflight checks

Before generating, verify:

1. **Story file exists**: `campaigns/[CAMPAIGN]/party/session-[N]/session-[N]-story.md`
   - If missing: *"Story file not found. Run the story-teller first: `/dm-end-session` or ask me to write the story for session [N]."*

2. **Memoir JSONs exist**: `campaigns/[CAMPAIGN]/party/session-[N]/session-[N]-caelith.json` (and corrin, lylnyler)
   - If missing: *"Memoir files not found. Run the website-generator first: ask me to generate the website for session [N]."*

3. **Narrator voice exists**: `website/audio/introductions/narrator.pt`
   - If missing: *"Narrator voice not locked. Run `.claude/tools/audition-narrator.py` first, or `/dm-audition-voice [campaign] narrator`."*

4. **At least one character voice exists**: any `.pt` file in `website/[CAMPAIGN]/audio/introductions/`
   - If none: *"No character voices locked. Run `/dm-audition-voice [CAMPAIGN] [character-slug]` for each speaking character."*

5. **Speaker tags in story**: check that `[slug]:` tags exist in the story file. If none found, warn:
   *"Warning: no speaker tags found in the story file. Voices will not switch — all lines will use the narrator voice. Add `[character-slug]: \"dialogue\"` tags to the story to enable character voices."*

---

## Step 2b — Check for missing or placeholder voices

Before generating audio, scan the story file for all `[slug]:` speaker tags and identify who needs a real voice.

**How to check:**

1. Extract all unique speaker slugs from lines matching `^\[([^\]]+)\]:` in the story file.

2. For each slug, determine their voice status:
   - **Has a real voice**: a `.wav` exists at `website/[CAMPAIGN]/audio/introductions/[slug].wav` or `website/audio/introductions/[slug].wav`, and it is NOT a generic placeholder
   - **Has a placeholder voice**: mapped in `campaigns/[CAMPAIGN]/party/voice-overrides.json` to a `male-*` or `female-*` slug (e.g. `"male-gruff"`, `"female-warm"`) — generic, not character-specific
   - **Has no voice**: no `.wav` and not in `party/voice-overrides.json`

3. Flag a speaker as **needing attention** if they fall into either of the last two categories.

4. For each flagged speaker, count how many sentences of dialogue they have across the session (count `.`, `!`, `?` endings in their tagged lines).

**Prompting the DM:**

For each flagged speaker with more than 2 sentences of dialogue, stop and ask — one at a time:

> **[Slug]** — [N] sentences this session. Currently using: [*no voice* / *generic: male-gruff*].
> Would you like to generate a dedicated voice for them, keep the generic, or skip?
>
> - `generate` — run `/dm-audition-voice [CAMPAIGN] [slug]` now
> - `keep` — leave the current assignment as-is (or set narrator if they have no voice)
> - `skip` — narrator fallback, no override entry written

Wait for the DM's answer before moving to the next speaker.

- **generate**: invoke `/dm-audition-voice [CAMPAIGN] [slug]` and wait for it to complete before continuing.
- **keep** (no voice): add `"[slug]": "narrator"` to `campaigns/[CAMPAIGN]/party/voice-overrides.json`. Confirm: *"[Slug] will use the narrator voice."*
- **keep** (already has a placeholder): leave `party/voice-overrides.json` unchanged. Confirm: *"[Slug] keeps [current mapping]."*
- **skip**: no action — generate-audio.py falls back to narrator automatically.

For speakers with 2 or fewer sentences, skip silently — narrator fallback is fine without prompting.

---

## Step 3 — Generate scene audio

```bash
${TTS_PYTHON:-python3} .claude/tools/generate-audio.py [CAMPAIGN] campaigns/[CAMPAIGN]/party/session-[N]/session-[N]-story.md --scenes-only
```

Report progress as each scene completes.

---

## Step 4 — Generate memoir audio

```bash
${TTS_PYTHON:-python3} .claude/tools/generate-audio.py [CAMPAIGN] campaigns/[CAMPAIGN]/party/session-[N]/session-[N]-story.md --memoirs-only
```

Report progress as each memoir anchor completes.

---

## Step 5 — Confirm

Print a single line:
> "Audio generated — session [N], [X] scenes, [Y] memoir files."

Then, check `website/[CAMPAIGN]/sessions.json`. The `audioEnabled` flag is a **top-level field** (not per-session). If it is not `true`, add:
> "Set `audioEnabled: true` at the top level of sessions.json to show play buttons on all session pages."

---

## Options

The DM can pass additional flags after the session number:

- `--scenes-only` — skip memoir generation
- `--memoirs-only` — skip scene generation  
- `--scene [N]` — regenerate only scene N (e.g. after updating dialogue in the story)

Pass these through to `generate-audio.py` unchanged.
