---
description: Flush the current session conversation to the log file. Captures everything discussed since the last checkpoint. Use mid-session on long sessions or before a break.
argument-hint: "[campaign]"
---

Write the session conversation log directly from the active conversation context. Do NOT delegate to any agent — agents cannot access the raw conversation and will hallucinate content.

## Steps

1. Read `campaigns/$ARGUMENTS/party/state.md` to confirm the current session number N.

2. Read `campaigns/$ARGUMENTS/party/session-[N]/session-[N]-conversation.md` if it exists. Note the last logged scene heading so you only append what's new.

3. Write directly from the active conversation context — everything the DM said and Claude responded since the last checkpoint (or since session start if this is the first flush).

4. Append to `campaigns/$ARGUMENTS/party/session-[N]/session-[N]-conversation.md` using scene headings, DM/Claude speaker labels, and NPC dialogue quoted faithfully. See the format defined in the session conversation log header already in the file, or start fresh with `### [Time of Day] — [Location] — [Scene Name]` headings.

5. Quote DM inputs and NPC dialogue **exactly as they appeared in the conversation** — do not paraphrase, interpret, or reconstruct. If Caelith said "Hi, I'm Caelith Moorn" that is what goes in the log.

6. Print one confirmation line:
   > "Conversation log updated: campaigns/$ARGUMENTS/party/session-[N]/session-[N]-conversation.md (Manual checkpoint)"
