---
model: claude-haiku-4-5-20251001
name: session-context
description: RETIRED — no longer used. NPC conversations now use one warm `conversation-npc` agent per NPC (see .claude/rules/npc-memory.md). Do not spawn this agent.
tools:
  - Read
---

# Agent: Session Context — RETIRED

This agent has been retired. It used to hold the whole campaign state and spawn a `conversation-npc` agent per conversation with that state embedded (about 170 KB / 40,000 tokens re-written on every spawn, plus a relay hop for the opening scene). That made openings take 95–120 s and handed NPCs knowledge they could not have.

**Do not spawn it.** The replacement flow:

- The main thread spawns `conversation-npc` agents warm at session start (`WARM-UP`), one per likely NPC, in parallel.
- Each agent reads only its NPC file and its memory file (`party/npc-memory/[slug].md`).
- The main thread starts a conversation with `ACTIVATE`, passing only what the NPC can perceive and any DM-approved third-party information.

See `.claude/rules/npc-memory.md` and `.claude/agents/conversation-npc.md`.

If you are an instance of this agent and were spawned by mistake, reply with one line saying it is retired and stop.
