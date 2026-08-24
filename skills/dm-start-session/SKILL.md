---
description: Begin a play session — reads campaign state, shows party status, recaps last session, and tells the DM what comes next.
argument-hint: "[campaign name]"
---

Start session $ARGUMENTS

Delegate to the `session-manager` sub-agent (`subagent_type: "session-manager"`) to:
1. Read `campaigns/$ARGUMENTS/party/state.md`
2. Show current party status (HP, resources, conditions)
3. Show a brief recap of last session
4. Show active threads and calendar (location, quests, open threads, faction standings)
5. Predict 2–4 likely party actions this session based on state and source material
6. Flag any encounters likely to come up and prompt the DM to pre-validate them
7. Report all of this back to the main thread and end with "Ready to begin?"

`session-manager` is a one-shot agent — it returns this report and exits. It does not wait for the DM's confirmation and cannot act afterward.

**Once the DM confirms "Ready to begin" (or equivalent), the main thread itself — not session-manager — must spawn the `session-context` agent** (`subagent_type: "session-context"`, see `.claude/agents/session-context.md`) and record the agent ID **from the spawn result** — that is the only place the real ID appears; never take an ID from the agent's own reply text. Keep it for the rest of the session so NPC conversation requests can be routed to it via `SendMessage`. Do not treat the session as fully started until this spawn has actually happened — if the DM's confirmation is followed by other discussion instead of an immediate scene, spawn `session-context` at the point play actually resumes, not before the DM has confirmed.
