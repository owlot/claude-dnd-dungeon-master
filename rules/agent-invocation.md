# Agent Invocation

How to actually call a sub-agent. Applies to every skill and agent in this repo that delegates work.

---

## The call shape

Two parameters are mandatory on every `Agent` call:

```
Agent(
  subagent_type: "<exact name from .claude/agents/*.md frontmatter>",
  prompt: "Project root: <absolute path>\n<the rest of the prompt>",
  description: "<short label>"
)
```

### `subagent_type` — required, never inferred

Prose like *"delegate to the `session-manager` sub-agent"* does **not** select the agent. Only the `subagent_type` parameter does.

Omit it and the call silently succeeds as a `general-purpose` agent: none of the named agent's instructions, tool restrictions, or model choice apply. The work appears to happen — the agent is capable and will improvise something plausible — while following none of the rules the agent file exists to enforce. This failure is silent at the table and only visible afterwards in the transcript.

Valid values are the `name:` field of the agent files:

`character-creation`, `character-tracker`, `combat-tracker`, `conversation-log-appender`, `conversation-npc`, `encounter-verifier`, `indexer`, `scene-image-generator`, `session-manager`, `srd-lookup`, `story-teller`, `website-generator`

### `Project root:` — required first line of the prompt

Agents do not inherit the working directory. Every prompt starts with `Project root: <absolute path>`.

---

## Foreground vs background

Default is background. Pass `run_in_background: false` when the very next thing you do depends on the agent's answer — anything the DM is waiting on at the table.

A background spawn ends your turn the moment it is issued. The agent's completion notification then returns to *whoever spawned it*, not to the DM, and nothing forwards it automatically. For a live NPC line or a stat block the table is waiting on, that reads as "the answer never arrived."

---

## Long-lived agents: spawn once, reuse the ID

Some agents are meant to exist exactly once for a stretch of work — `conversation-npc` (one per NPC, warmed at session start, see `.claude/rules/npc-memory.md`), `combat-tracker` for a fight. For these, **the caller is the only party that can prevent duplicates.** A freshly spawned agent starts with empty context and cannot tell that a sibling is already running; asked to load, it will dutifully re-read everything while the table waits.

So the rule lives with the caller:

- Spawn it **once**, and keep the agent ID from the spawn result.
- Every later interaction is `SendMessage` to that ID — never a second `Agent` call.
- If a message to it fails, resend to the correct ID. **Never spawn a replacement** to work around a bad address; that creates the duplicate you were avoiding and starts a cold reload.
- Before spawning one of these, ask whether this session already has one. If yes, you want `SendMessage`, not `Agent`.

## Watching a long conversation

An agent cannot judge its own context size or how many turns it has run, so it cannot warn you when it starts to bog down — tested at 16 exchanges, a `conversation-npc` instructed to raise the issue itself never did.

The count is trivially observable from the caller's side, because the log has one heading per exchange:

```bash
grep -c '^## Exchange' "campaigns/[name]/party/session-[N]/session-[N]-npc-[seq]-[slug].md"
```

Context grows steadily on top of a large baseline. Measured across a 16-exchange conversation: **32k → 44k input tokens**, roughly 750 tokens per exchange. A 44-turn conversation in an earlier session reached 108k and was visibly slow per line.

So there is no cliff, just a gradient — and note that a single agent turn handling several batched exchanges at once is far slower than the same exchanges sent one at a time (measured: 24–48s for one or two, 95–98s for four). If the DM is waiting, send one exchange per message rather than queueing several.

Past roughly 20 exchanges, if lines are getting slower, offer the DM the choice: end the conversation and respawn the NPC with a summary of what was established, or keep going with full fidelity. Never make that call silently — and never ask the agent to compress its own context, which trades the accuracy of the scene for speed the DM did not ask for.

## Agent IDs

**An agent cannot see its own ID.** The harness assigns it and returns it to the caller alongside the reply. An agent asked to state its own ID will invent a plausible-looking string that addresses nothing.

The caller keeps the ID from the spawn result and uses it for follow-up `SendMessage` calls. When one agent spawns another, the parent *does* receive the child's real ID in the spawn result — copy it from there verbatim, never from memory.

---

## Returning work to the caller

**Only an agent's final text block reaches the caller.** Text emitted before a tool call is replaced by whatever the agent writes after it.

Any agent whose output is meant to be read aloud or acted on directly must therefore end its turn on that content — never on a status line like *"log written, standing by."* Bookkeeping goes before the payload, or inside it; never after.
