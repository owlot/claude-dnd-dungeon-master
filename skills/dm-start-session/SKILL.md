---
description: Begin a play session — reads campaign state, shows party status, recaps last session, and tells the DM what comes next.
argument-hint: "[campaign name]"
---

Start session $ARGUMENTS

Delegate to the `session-manager` sub-agent to:
1. Read `campaigns/$ARGUMENTS/party/state.md`
2. Show current party status (HP, resources, conditions)
3. Show a brief recap of last session
4. Show active threads and calendar (location, quests, open threads, faction standings)
5. Predict 2–4 likely party actions this session based on state and source material
6. Flag any encounters likely to come up and prompt the DM to pre-validate them
7. Ask "Ready to begin?" and wait for the DM to confirm
8. Spawn the `session-context` agent and hand its ID to the main thread, so NPC conversation requests can be routed to it via `SendMessage` for the rest of the session
