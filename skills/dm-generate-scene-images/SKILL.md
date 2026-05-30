---
description: Pick and generate scene images for a session — spawns the scene-image-generator sub-agent which reads the session HTML, recommends cinematic moments, generates landscape PNGs, and wires them into the HTML. DM approves each image via SendMessage before it is inserted.
argument-hint: "[campaign-slug] [session-number] — e.g. 'waterdeep-dragon-heist 11'"
---

Generate scene images for session: $ARGUMENTS

## Step 1 — Parse arguments

Split `$ARGUMENTS` into:
- `CAMPAIGN` = first word (e.g. `waterdeep-dragon-heist`)
- `SESSION` = second word (e.g. `11`)

If either is missing, ask the DM.

## Step 2 — Spawn the scene-image-generator agent

Spawn the `scene-image-generator` sub-agent with:

```
Project root: [absolute path to project root]
Campaign: [CAMPAIGN]
Session: [SESSION]
```

The agent handles everything from here: reading the session HTML, recommending scenes, generating images, and wiring them into the HTML. It will send messages back asking for approval after each image — relay those to the DM and forward the DM's replies back to the agent via SendMessage.

Do not read the session HTML, build prompts, or run the image generator in the main context — that all happens inside the agent.
