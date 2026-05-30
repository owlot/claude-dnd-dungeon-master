---
description: Recovery skill — rebuilds the session conversation log from the raw JSONL transcript when the normal incremental flow failed or context was lost. Use only when the conversation log is missing or incomplete.
---

# Recover Session Log

This skill is a fallback for when the normal incremental session log is missing or incomplete. It reads the raw JSONL transcript of the session directly and reconstructs `session-[N]-conversation.md` from it.

**Only use this when:**
- The conversation log is missing or incomplete
- The conversation log file is missing or truncated
- Something went wrong with the incremental checkpoints during the session

Do not use this as the default flow — /dm-checkpoint-log handles normal logging from active context.

---

## Step 1 — Read campaign state

Read `campaigns/[name]/party/state.md` to get the current session number N.

---

## Step 2 — Extract the raw transcript

Run the extraction script, passing the campaign name:

```bash
python3 .claude/scripts/extract_jsonl.py [campaign-name] --session [N]
```

Pass `--session N` with the session number being recovered (e.g. `--session 8`). The script searches for the correct JSONL file by looking for `start session N` in the transcript, then falls back to chronological ordering of session invocation files. It prints the selected file path to stderr — **always verify this is the correct file** before proceeding.

If the script selects the wrong file, override it explicitly:

```bash
python3 .claude/scripts/extract_jsonl.py [campaign-name] --session [N] --file /path/to/correct.jsonl
```

The `--file` flag bypasses all selection logic and uses the specified file directly.

If the script reports no JSONL file found, check that the campaign name is correct and that the session was run from this project directory.

---

## Step 3 — Scope the transcript

Only use exchanges that fall between the `/dm-start-session` invocation and `/dm-end-session` (or the point where the session ended). Do not read beyond those boundaries.

Skip any tool result blocks that contain the text of an existing log or memoir file — these are file reads, not session events. Only process `[DM]` inputs and `[ASSISTANT]` narrative/ruling responses.

---

## Step 4 — Prepare the log file

The log file is `campaigns/[name]/party/session-[N]/session-[N]-conversation.md`.

If the file does not exist yet, write this header first:

```markdown
# Session [N] Conversation Log — [Campaign Name]

**Date**: [real-world date]
**Location**: [starting location] → [ending location]
**Players**: [Player Name] ([Character Name]), ...

---
```

If the file has partial content, read it first and note the last logged section — append only after that point. Do not overwrite what is already there.

---

## Step 5 — Write the recovered log

Append scene sections using this format:

```markdown
### [Time of Day] — [Location] — [Scene Name]

**DM**: [what the DM said or reported]

*Claude: [what Claude responded, prompted, or ruled]*

**DM**: [next input]

*Claude (as [NPC Name]):* [NPC dialogue in the NPC's voice]
> *[Read-aloud narration or atmospheric description, if any]*
```

**Time of day labels**: Early Morning / Mid Morning / Late Morning / Noon / Early Afternoon / Mid Afternoon / Late Afternoon / Evening / Late Evening / Night / Late Night / Midnight

**Combat cross-references**: Write one line and stop — do not narrate the combat:
```markdown
*(See full combat log: session-[N]-combat-[slug].md)*
```

**NPC conversation cross-references**: Write one line and stop — the conversation-tracker already appended those:
```markdown
*(See NPC log: session-[N]-npc-[sequence]-[slug].md)*
```

**What to omit**: Combat round-by-round detail, rules discussions that didn't affect the fiction, out-of-character table talk.

---

## Step 6 — Recover private logs (if any)

Private exchanges must never appear in the shared conversation log. Check the transcript for:
- Patron or deity communications directed at one PC
- Sending spells or magical messages received by one PC
- Secrets the DM passed to one player privately
- A PC's internal monologue or vision if the DM ran it one-on-one
- Anything explicitly marked as private or for one player's eyes
- **Actions taken while physically separated from the party** — if a PC splits off and does things the other PCs cannot see (pickpocketing, placing bets under an alias, solo intelligence gathering), those actions are private. Only what the PC chose to tell the party afterward goes in the shared log.

In the shared log, replace the private section with a one-line summary of what the PC reported back: e.g. *"Corrin rejoined the group. He mentioned he'd gathered some useful intelligence from the crowd."* — no detail on what he actually did or found.

For each character with private content, write or append to `campaigns/[name]/party/session-[N]/session-[N]-private-[character].md`:

```markdown
# Session [N] Private Log — [Character Name]
**Campaign:** [name]
**Player:** [player name]

*This file contains private exchanges between the DM and [Character Name]'s player. Do not share with other players.*

---

### [Time of Day] — [Scene Name]

*Claude (as [Patron/Spirit/Voice]):* "[dialogue]"

*[DM note: what this means mechanically or narratively — for story-teller reference.]*
```

If the file already has partial content, append only — do not overwrite.

---

## Step 7 — Recover combat logs (if any)

Check whether combat logs are missing for any fights that occurred this session. Compare fights found in the JSONL transcript against existing `campaigns/[name]/party/session-[N]/session-[N]-combat-*.md` files.

For each fight with no existing combat log, write `campaigns/[name]/party/session-[N]/session-[N]-combat-[slug].md` using the combat-tracker's log format.

**Critical rules for combat log recovery — this is extraction, not summarisation:**
- Read the transcript **sequentially and completely** — do not compress or summarise rounds
- **Copy verbatim** from the transcript: attack rolls, damage values, HP totals, narration, crowd reactions, NPC dialogue, DM rulings, atmospheric descriptions — everything Claude wrote during the fight
- **Copy combat status blocks verbatim** — they appear in the transcript as `== COMBAT: Round N ==` tables; include every one of them exactly as written
- **Copy narration verbatim** — audience reactions, arena atmosphere, NPC behaviour between turns; these appear as prose paragraphs in the transcript between mechanical exchanges
- Track round numbers by counting turn sequences in the transcript, not by guessing
- Write every turn in the order it appears — do not reorder
- If something is unclear or missing from the transcript, write `[unclear from log]` — never invent or infer values
- Attribution matters: always verify who performed each action from the transcript — do not assume

Format:
- Combatants table (starting HP, AC)
- Initiative order (exact rolls as reported)
- Round-by-round turns: for each turn, copy the full exchange — the mechanical result AND any narration that followed it
- Combat status blocks: copy each `== COMBAT ==` block verbatim after the turn that triggered it
- Post-combat section (healing, loot, XP)
- Final party status

---

## Step 8 — Confirm

Print one line per file written or recovered:
> "Session log recovered: campaigns/[name]/party/session-[N]/session-[N]-conversation.md"
> "Private log recovered: campaigns/[name]/party/session-[N]/session-[N]-private-[character].md" *(if applicable)*
> "Combat log recovered: campaigns/[name]/party/session-[N]/session-[N]-combat-[slug].md" *(if applicable)*

**Stop here.** Do not write the story. Do not delegate to the story-teller or any other agent. The DM triggers story generation separately with "write the story for session [N]".
