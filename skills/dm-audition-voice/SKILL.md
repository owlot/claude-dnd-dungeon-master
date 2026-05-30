---
description: Create or update an introduction file for a character and audition 4 voice samples. Use when adding a new NPC or PC who needs a locked voice for audio generation.
argument-hint: "[campaign-slug] [character-slug] — e.g. 'waterdeep-dragon-heist vajra-safahr'"
---

Create or update a voice introduction for: $ARGUMENTS

## Overview

This skill:
1. Creates or updates the voice section in `campaigns/[campaign]/info/npcs/[character-slug].md`
2. Runs `.claude/tools/audition-voice.py` to generate and play 4 voice samples
3. Locks in the chosen voice with `.claude/tools/lock-voice.py` (which creates the `.pt` directly — no rebuild step needed)

**Project root:** use the absolute project root for all paths and commands.

---

## Step 1 — Parse arguments

Split `$ARGUMENTS` into:
- `CAMPAIGN` = first word (e.g. `waterdeep-dragon-heist`)
- `CHARACTER` = second word (e.g. `vajra-safahr`)

If only one argument is given, ask the DM for the campaign slug.

---

## Step 2 — Resolve character file path

- **NPC**: file is at `campaigns/[CAMPAIGN]/info/npcs/[CHARACTER].md`
- **PC**: file is at `campaigns/[CAMPAIGN]/party/characters/[CHARACTER].md`
- **Generic voice template** (slugs: `male-young-minor`, `male-mid-minor`, `male-weathered-minor`, `female-young-minor`, `female-mid-minor`): file is at `campaigns/[CAMPAIGN]/info/introductions/[CHARACTER].md` — skip to Step 4, using the default introduction text: *"I don't usually talk to strangers about things that aren't my business. But you asked, so. Make it quick."*

Check if the resolved file exists.

- **If it exists**: Read the `## voice` section and show the DM the current voice descriptors and introduction text. Ask: *"Do you want to update the voice section before auditioning, or audition with the current text?"*
- **If it doesn't exist**: Proceed to Step 3 to create one.

---

## Step 3 — Create or update the voice section

If creating a new NPC file (or adding a `## voice` section to an existing one), gather from the DM (or derive from campaign files):

- **voice descriptors**: pitch, pace, tone, quality, notes
- **introduction text**: A first-person self-introduction in the character's own voice — 3–5 sentences. This is what the voice model reads to generate the reference clip. It should capture who they are and how they speak, not just what they do.

Introduction text rules:
- Always first person ("I am...", "I work...", "I've been...")
- Captures personality and speech patterns, not just facts
- 3–6 sentences — enough for a meaningful voice sample (~15–25 seconds)
- Should sound like something the character would actually say if introducing themselves

Write or update the `## voice` section in the character file using this format:
```markdown
## voice
pitch: [description]
pace: [description]
tone: [description]
quality: [description]
notes: [longer note about speech patterns and character]
instruction: "[optional — override instruction for the TTS model]"

[First-person introduction text]
```

---

## Step 4 — Run the audition script

```bash
python3 .claude/tools/audition-voice.py [CAMPAIGN] [CHARACTER]
```

This generates 4 WAV files at `website/[CAMPAIGN]/audio/introductions/[CHARACTER]_audition_1.wav` through `_4.wav`.

---

## Step 5 — Lock in the chosen voice

Ask: *"Which number do you want to lock in? Or type 'again' to generate 4 more samples."*

- If the DM picks a number (1–4):

```bash
python3 .claude/tools/lock-voice.py [CAMPAIGN] [CHARACTER] --wav website/[CAMPAIGN]/audio/introductions/[CHARACTER]_audition_[N].wav
```

- If the DM says 'again': go back to Step 4 and regenerate.

---

## Step 6 — Confirm

Report:
> "Voice locked: [CHARACTER] → `website/[CAMPAIGN]/audio/introductions/[CHARACTER].pt`"
