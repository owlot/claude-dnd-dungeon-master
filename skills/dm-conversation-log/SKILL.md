---
description: Write an NPC conversation log from the current conversation history. Use to retroactively archive an NPC conversation that happened before the conversation-tracker was running.
argument-hint: "[campaign] [npc-slug]"
---

Write the NPC conversation log directly from the active conversation context. Do NOT delegate to the conversation-tracker agent — it cannot access the raw conversation and will hallucinate content.

## Steps

1. Read `campaigns/$ARGUMENTS/party/state.md` to get the current session number N.

2. Read `.claude/rules/npc-log-format.md` for the exact file location, naming convention, format, and formatting rules.

3. Find the conversation in the active conversation context — locate the NPC's opening, every exchange in order, any roll results, disposition shifts, and how the conversation ended.

4. Write the NPC log file directly from what appears in the conversation. Quote party inputs and NPC responses verbatim — do not paraphrase.

5. Where anything is unclear or missing from the conversation context, write `[unclear from log]` — never invent or infer values.

6. Delegate to the `conversation-log-appender` agent with an explicit prompt:

   > "Append the NPC conversation from `campaigns/[name]/party/session-[N]/session-[N]-npc-[seq]-[slug].md` to `campaigns/[name]/party/session-[N]/session-[N]-conversation.md`. NPC file is at `campaigns/[name]/info/npcs/[slug].md`."

7. Print one confirmation line:
   > "NPC log written: campaigns/[name]/party/session-[N]/session-[N]-npc-[sequence]-[slug].md"
