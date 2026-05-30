---
description: Write a combat log from the current conversation history. Use in a resumed old session to retroactively archive a fight that happened before the combat tracker wrote the log automatically.
argument-hint: "[campaign] [encounter-slug]"
---

Write the combat log directly from the active conversation context. Do NOT delegate to the combat-tracker agent — it cannot access the raw conversation and will hallucinate content.

## Steps

1. Read `campaigns/$ARGUMENTS/party/state.md` to get the current session number N.

2. Read `.claude/rules/combat-log-format.md` for the exact file location, format, and formatting rules.

3. Find the fight in the active conversation context — locate initiative rolls, all turns in order, damage reported, HP changes, conditions, and post-combat events.

4. Write the combat log directly from what appears in the conversation. Copy verbatim:
   - Attack rolls, damage values, HP totals
   - Combat status blocks (`== COMBAT: Round N ==`)
   - Narration and atmospheric descriptions
   - DM rulings and outcomes

5. Where anything is unclear or missing from the conversation context, write `[unclear from log]` — never invent or infer values.

6. Print one confirmation line:
   > "Combat log written: campaigns/[name]/party/session-[N]/session-[N]-combat-[slug].md"
