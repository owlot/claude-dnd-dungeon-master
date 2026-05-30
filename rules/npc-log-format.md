# NPC Conversation Log Format

Reference for both the `conversation-tracker` agent (live conversations) and the `/dm-conversation-log` skill (retroactive from context).

---

## File location

`campaigns/[name]/party/session-[N]/session-[N]-npc-[sequence]-[slug].md`

Where:
- `[name]` = exact campaign folder name (e.g. `waterdeep-dragon-heist`)
- `[N]` = session number from `party/state.md`
- `[sequence]` = zero-padded incrementing number (01, 02, 03...) — determines chronological order within the session
- `[slug]` = NPC name slug (e.g. `mira`, `vajra-safahr`)

To determine the sequence number: use Glob to list `campaigns/[name]/party/session-[N]/session-[N]-npc-*.md`, count the results, and add 1. If no files match, the first conversation is `01`.

If `campaigns/[name]/party/session-[N]/` does not exist, stop and report: *"Campaign session folder not found: campaigns/[name]/party/session-[N]/. Check the campaign name and session number and try again."* Do not create the directory.

---

## Format

```markdown
# Conversation Tracker: [NPC Name]
**Session**: [N]
**Campaign**: [name]
**Location**: [current location]
**NPC Disposition at start**: [Hostile / Suspicious / Neutral / Warming / Friendly / Allied]

---

## Exchange 1

**Party**: [exactly what the DM sent — verbatim, including all context, actions, and what the party said or did. Never paraphrase.]

**[NPC Name]**: [The full agent response as delivered — narration, action beats, body language, atmosphere, AND all NPC dialogue. Copy verbatim. Do not strip narration. Do not summarise. If the NPC called out a name while leaving, that belongs here. If the NPC's hand moved toward a weapon, that belongs here. Everything the agent wrote is part of the response.]

---

## Exchange 2
...

---

## Conversation End

**Final disposition**: [disposition]

**Information revealed**:
- [bullet list of each piece of information the NPC shared]

**Information withheld**:
- [bullet list of information the NPC had but did not share, and why]

**Commitments made**:
- [any promises, deals, or agreements made by either side — or "None"]

**Next beat**:
[What the NPC is waiting for, expects next, or will do next. One or two sentences.]
```

---

## Formatting rules

- Party inputs are **always verbatim** — copy the full DM input, never paraphrase
- NPC responses are copied in full as delivered — narration, action beats, and all dialogue. Do not strip anything. A one-word callout the NPC makes to a third party while leaving the scene is as important as a long speech. Copy everything the agent wrote.
- If a skill check occurred, include the result inline: `*Persuasion 18 — Vajra leans forward.*`
- Disposition shifts are noted inline after the exchange that caused them:
  `*[Disposition shift: Neutral → Warming — party mentioned Roxley's name]*`
- If the DM corrects something mid-conversation, append immediately after the original exchange — do not rewrite it:
  ```
  [DM correction: ...]
  **[NPC Name] (revised)**: [revised response]
  ```
- Where detail is missing or unclear (retroactive logs only), write `[unclear from log]` — never invent or infer
- **Correct spelling mistakes and proper name typos** — use canonical spellings in the log (e.g. "Caelith Morn" not "Caelith Moorn", "Torm" not "Torn", "Xanathar" not "Xantahar"). The DM types quickly; the log should be clean.

---

## Disposition scale

| Level | Meaning |
|-------|---------|
| Hostile | Actively working against the party; may attack or refuse all interaction |
| Suspicious | Guarded, evasive; shares little; may be watching for threats |
| Neutral | Default; willing to interact; will share what is safe to share |
| Warming | Party has earned some goodwill; more forthcoming; starting to trust |
| Friendly | Actively helpful within their means; will share more than strictly required |
| Allied | Committed to the party's cause in this matter; will take some risk to help |
