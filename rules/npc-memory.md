# NPC Memory and Warm Agents

How NPC conversation agents know things, and how they are started. Applies to `conversation-npc`, the main thread, and `session-manager`.

---

## The principle

An NPC knows exactly three things:

1. **Its NPC file** (`info/npcs/[slug].md`) — background, voice, secrets, what it would plausibly share.
2. **Its own past conversations** with the party — kept in its memory file (`party/npc-memory/[slug].md`).
3. **Third-party information the DM has approved** — see *Third-party leaks* below.

Everything else the party did — in other scenes, with other NPCs, elsewhere in the city — is **not** the NPC's knowledge. Agents are never given a general state digest, the party's full state, or "what happened since session start". Anything not in the three sources above does not exist for the NPC, and the NPC plays honest ignorance.

---

## The memory file

`campaigns/[name]/party/npc-memory/[slug].md` — one per NPC who has spoken with the party. Written and updated only by the conversation agent (at the end of each conversation) and, for approved leaks, by the main thread.

```markdown
# NPC memory: [Display Name] ([slug])

_What this NPC knows from conversations with the party. Appended at the end of every conversation._

## What they know about the party
- Names and aliases they know each PC by; faces they have seen; what the PCs have shown or given them

## Conversation history
### Session [N] — [scene, location]
- **Learned from the party**: …
- **Told the party**: …
- **Withheld / lied about**: …
- **Commitments**: …
- **Disposition after**: [Hostile / Suspicious / Neutral / Warming / Friendly / Allied]

## Third-party information (DM-approved)
- [Session N] Heard from [source]: [fact]

## Waiting for / open
- What the NPC expects or is waiting for next
```

If the file does not exist the NPC has had no conversation with the party: play a first meeting from the NPC file alone.

---

## Warm pool — start of session

After the DM confirms "Ready to begin", the main thread spawns one `conversation-npc` agent per likely NPC, **all in one message so they run in parallel**, while the DM reads the briefing. The list comes from the session-manager's `LIKELY NPCS` section (NPCs tied to the likely actions and open threads; aim for 4–6).

Spawn call: `subagent_type: "conversation-npc"`, `name: "npc-[slug]"`, and a prompt that begins `WARM-UP` and contains only: project root, campaign, NPC slug, session number. A warm-up agent reads its NPC file and its memory file, then replies with one line (`Ready: [Name], disposition [x]`) and stops. It does **not** create a log file.

NPCs that are not in the pool are spawned the same way (warm-up, then activate) the moment they come up. Spawn once per NPC per session and keep the agent for every later conversation with that NPC; reach it with `SendMessage` to `npc-[slug]` (or its ID from the spawn result). Never spawn a replacement for an agent that already exists.

---

## Activating a conversation

When a named NPC conversation begins (after `/dm-checkpoint-log`), the main thread sends the agent a message that starts `ACTIVATE` and contains only:

- **Location / time**
- **Present**: who from the party is in the scene
- **Perceivable**: what the NPC can see or hear in the scene (not what the party knows)
- **Third-party** (only if the DM approved it): facts the NPC could plausibly have heard from someone else, with the source
- **Disposition**: the NPC's current disposition if it differs from the memory file
- **First input**: the DM's input, verbatim

The agent creates the NPC log (next sequence number), then returns the opening scene. Every later exchange is a plain message to the same agent: the DM's input verbatim, plus any roll result. Standing DM rulings (species, pronouns, what the NPC does not know) belong in the NPC file, not in every message.

---

## Third-party leaks

When a scene might let an NPC know something it did not hear in its own conversations — it could plausibly have heard it from another NPC, a rumor, a Watch report, a messenger — the **main thread proposes the leak to the DM** ("Renaer would plausibly have heard from Vajra that Meloon was freed — approve?") and waits. Only approved leaks are passed, in the `Third-party` line of the activation message, and appended by the main thread to the NPC's memory file under *Third-party information*. Unapproved leaks do not exist for the NPC.

---

## Logging and memory updates

- **Header**: the agent writes the opening header of the NPC log when it is activated.
- **Each exchange**: the **main thread** appends it to the NPC log with a single `cat >>` heredoc (`.claude/rules/npc-log-format.md`) *after* relaying the scene to the DM, so the DM reads while the file is written. The agent returns the scene only.
- **End of conversation**: the agent appends the `Conversation End` block, appends a new `### Session [N]` entry to its memory file (from the Conversation End content), and returns the completion line. It keeps its context: a later conversation with the same NPC is a new `ACTIVATE` on the same agent, with a new log file.
