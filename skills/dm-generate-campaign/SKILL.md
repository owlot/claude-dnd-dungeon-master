---
description: Walk the DM through generating a new campaign — hook, structure, starting location, factions, key NPCs, and session zero prep. Outputs an initial state.md and a primer the DM can hand to players.
argument-hint: "[campaign name] [optional: tone or theme]"
---

Generate a new campaign: $ARGUMENTS

Reference `.claude/rules/character-sheets.md` for the state.md format and `.claude/dnd-5e-srd/markdown/` for rules context.

## Step 1 — Establish the concept

Ask the DM:
1. *"What's the tone? (dark fantasy / heroic adventure / political intrigue / horror / other)"*
2. *"What level do players start at?"*
3. *"Do you have a setting in mind, or should I generate one?"*
4. *"Any themes or content to avoid?"*

Wait for answers before continuing.

## Step 2 — Generate the hook

Choose or adapt one hook type:

- **The Patron**: Someone hires the party for a job
- **The Threat**: Danger comes to the party or someone they care about
- **The Discovery**: Something found leads to adventure
- **The Wronged**: Justice demands action

Present 2–3 hook options based on the tone the DM chose. Let them pick or combine.

## Step 3 — Starting location

Define the home base:
- Name and brief description (one sentence)
- Three truths: one obvious, one discoverable, one secret
- Three named NPCs: a friendly face, a neutral authority, a potential complication
- One nearby danger that drives the first session

## Step 4 — Factions (2–3)

For each faction:
- **Goal**: What do they want?
- **Methods**: How do they pursue it?
- **Leader**: One named NPC
- **How they relate to the party**: Initial disposition (Hostile / Neutral / Friendly)

## Step 5 — Campaign arc outline

Sketch the three-act structure:
- **Act 1 (sessions 1–3)**: Hook and commitment
- **Act 2 (sessions 4–8)**: Escalation and revelations
- **Act 3 (sessions 9+)**: Confrontation and resolution

Keep each act to 2–3 bullet points. The DM fills in the details as play unfolds.

## Step 6 — Session zero checklist

Remind the DM to cover with players:
- Tone and content expectations
- Character connections (why are they together?)
- Player goals
- Lines and veils
- Scheduling

## Step 7 — Write output files

Create `campaigns/[name]/party/state.md` using the standard template:

```markdown
# [Campaign Name]

## Current State
- **Session**: 0
- **In-Game Date**: [date or "unknown"]
- **Location**: [starting location]

## Party
| Name | Class/Level | HP | Notes |
|------|-------------|----|----|
| [DM: fill in after character creation] | | | |

## Active Quests
- [ ] [Opening quest from the hook]

## Last Session Summary
[None yet — campaign not started]

## Next Session Prep Notes
[DM: complete after session zero]

## Open Threads
- [Hook thread]

## Key NPCs
[From step 3 and 4 above]

## Factions
[From step 4 above]

## DM Notes
[Hook, arc outline, and session zero notes from this generation]
```

Also write `campaigns/[name]/campaign-primer.md` — a one-page player-facing summary of the world, tone, and starting situation. No spoilers.

Print: *"Campaign generated. Run `/dm-create-characters [name]` to create the party, then `/dm-index-campaign [name] from [filename]` if you have a source document (place the source file in `campaigns/[name]/sources/` first)."*
