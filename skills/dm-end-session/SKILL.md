---
description: Wrap up a play session — flush the conversation log, derive a summary from it, then update state.md, all character files, and append a session log entry.
argument-hint: "[campaign]"
---

End session $ARGUMENTS

1. **Invoke `/dm-checkpoint-log $ARGUMENTS` first** — flush the conversation log directly from active context before spawning any agent.

2. Delegate to the `session-manager` sub-agent (`subagent_type: "session-manager"`) to:
   1. Derive the session summary from the conversation log just written
   2. Update `party/state.md` with current situation, open threads, next steps, and its `## Objects` and `## Locations` tables; append what changed to each affected `party/objects/[slug].md` and `party/locations/[slug].md` ledger (the DM approves the rows first)
   3. Update every character file in `campaigns/[campaign]/party/characters/` with current HP, resources used, gold, notes
   4. Append a session log entry to `party/session-log.md`
   5. List all files touched with a one-line description of what changed

3. **Write the story in two runs** (each foreground, `subagent_type: "story-teller"`, prompt starts with `Project root:` then the phase line):
   1. `PHASE: LEDGER` — writes `session-[N]-facts.md` including its Coverage list. Reply: `LEDGER DONE`.
   2. `PHASE: STORY` — reads the ledger, writes `session-[N]-story.md`, completes the pre-flight, writes `session-[N]-story-preflight.md`.

   **Gate:** if the story-teller errored, was cut off (rate limit, context), or `session-[N]-story-preflight.md` does not exist, the story is an unfinished draft — rerun `PHASE: STORY` (the ledger is kept). Never validate or publish a story without its pre-flight file.

4. **Validate the story** with the `story-validator` agent (`subagent_type: "story-validator"`), one validator per block of scenes, all spawned in **one parallel message**.
   - **Blocks:** split the story at its `## ` scene headings into blocks of similar size — roughly one block per 8–10 KB of story, minimum one, maximum four (a short session gets one or two validators, not four).
   - **Slice the inputs** so no validator reads what it does not need. For each block find, with `grep -n`, (a) the block's story line range (its first scene heading to the line before the next block's first heading), (b) the matching line range(s) of `session-[N]-conversation.md` (its `### ` scene headings carry times and places; cover the same events), (c) the NPC log files for the NPCs in the block.
   - **Prompt per validator:** `Project root:`, campaign, session N, the block label (A–D), the story's full list of `## ` scene headings (for orientation), `Story lines: X–Y`, `Conversation log lines: A–B[, C–D]`, `NPC logs: [files]`, and the report path `tmp/story-validation-[A-D].md`. Spawn with `name: "validator-[A-D]"` so each can be messaged again.
   - Wait for all reports.

5. **Apply the findings** to `session-[N]-story.md` yourself (the story file is the single source of truth; validators never edit). Replacement text must follow the story style rules: no dice numbers, PCs named in the third person, nothing a character could not know. Fixes that change a memoir require the website-generator rerun.
   **Then re-check:** send each validator `RE-CHECK` with its block's new story line range (line numbers shift after edits; recompute them). The validator still holds its block's sources, so this is cheap; it confirms each finding is resolved and catches errors the fixes introduced (invented facts, dice numbers). Apply anything it reports and repeat once if needed.
   Finally write `campaigns/[campaign]/party/session-[N]/session-[N]-story-validation.md`: findings by type, what was fixed, anything deliberately left, that the re-check passed, and the date.

6. Tell the DM the story is validated and ready for review. The website (`website-generator`) and audio run only after the DM asks.
