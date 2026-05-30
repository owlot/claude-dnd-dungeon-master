---
description: Walk through character creation for all players before the first session. Delegates to the character-creation sub-agent.
argument-hint: "[campaign name]"
---

Create characters for campaign $ARGUMENTS

Delegate to the `character-creation` sub-agent. That agent asks class- and race-specific questions only — not a generic checklist — and writes one character file per PC to `campaigns/$ARGUMENTS/characters/`.
