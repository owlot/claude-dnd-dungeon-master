---
description: Wrap up a play session — flush the conversation log, derive a summary from it, then update state.md, all character files, and append a session log entry.
argument-hint: "[campaign]"
---

End session $ARGUMENTS

1. **Invoke `/dm-checkpoint-log $ARGUMENTS` first** — flush the conversation log directly from active context before spawning any agent.

2. Delegate to the `session-manager` sub-agent to:
   1. Derive the session summary from the conversation log just written
   2. Update `party/state.md` with current situation, open threads, next steps
   3. Update every character file in `campaigns/[campaign]/party/characters/` with current HP, resources used, gold, notes
   4. Append a session log entry to `party/session-log.md`
   5. List all files touched with a one-line description of what changed
