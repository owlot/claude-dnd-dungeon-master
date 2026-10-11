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

**Once the DM confirms "Ready to begin" (or equivalent), the main thread itself — not session-manager — warms the NPC agents.** Read the `LIKELY NPCS` section of the report and, in **one message with several parallel `Agent` calls**, spawn one agent per slug: `subagent_type: "conversation-npc"`, `name: "npc-[slug]"`, prompt `WARM-UP` plus project root, campaign, NPC slug and session number (see `.claude/rules/npc-memory.md`). Record each agent's ID from the spawn result. A warm-up agent replies `Ready: …` and does not create a log. Later conversations are started by messaging the agent `ACTIVATE …`; NPCs not in the pool are spawned the same way when they come up. Spawn at the point play actually resumes, not before the DM has confirmed. The old `session-context` agent is retired.
