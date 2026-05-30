---
description: Format all scene narration, NPC dialogue, and DM guidance consistently — read-aloud text the DM speaks at the table, separated from DM-only context Claude provides as insight. Apply automatically during any D&D session narration, NPC interaction, location description, or scene setup.
---

# Narration Format

Every response that presents a scene, describes a location, or voices an NPC must use this two-layer format. Never mix the layers.

---

## Layer 1 — Read-aloud text

This is what the DM speaks aloud to the players. It is written **in italics and/or as a blockquote**, in present or past tense, from the perspective of what the characters can perceive.

**Rules:**
- Only what the characters can see, hear, smell, or feel
- No hidden information, no NPC motivations, no faction identities the party hasn't learned
- No mechanical terms (HP, AC, CR, saving throw, spell slot)
- No map/room labels from encounter or source files (X18, Q7, area X3, etc.) — these are DM notation, not in-world language. Use descriptive names instead: "the audience chamber", "the sewer junction", "his private sanctum". Room labels belong in the `[DM: ...]` layer so the DM can cross-reference with maps.
- Named NPCs only if the party already knows the name — otherwise describe appearance only
- Keep it short: 2–5 sentences for a location, 1–3 sentences for an NPC entrance

**Format:**

> *The alley is narrow and smells of old rain. A figure leans against the far wall — heavy coat, hood up, watching the entrance.*

Or for NPC dialogue, use a blockquote with the name if known:

> *"I don't deal in names,"* the man says. *"I deal in coin."*

---

## Layer 2 — DM insight

This is context, mechanical information, and guidance **for the DM only**. It never reaches the players.

**Always written in square brackets:** `[DM: ...]`

**Rules:**
- Always on its own line, below the read-aloud text
- Never inline with the read-aloud — the DM must be able to read aloud the non-bracketed text without pausing
- Include: NPC's true name (if unknown to party), hidden motive, likely DC for any check, faction affiliation, what the NPC knows and won't say, what would change their attitude, mechanical notes, room/area labels (X18, Q7, etc.) so the DM can cross-reference with maps

**Format:**

`[DM: This is Urstul Floxin — Zhentarim enforcer. He knows where the Stone is but won't volunteer it. Persuasion DC 15 to get a name; Intimidation DC 13 if the party has leverage.]`

---

## Full example — NPC encounter

> *The door opens onto a halfling man in his fifties — magnifying lenses pushed up on his forehead, ink on three fingers, and the expression of someone interrupted mid-task. He looks at the party the way a person looks at weather: noting it, categorising it, not particularly concerned.*
>
> *"We're closed."*

`[DM: This is Ott Steelquill. He is not afraid — he doesn't know why they're here yet. He sold components and considers himself professionally uninvolved. He will cooperate if the party is direct and non-threatening; he has no stake in protecting the buyer. If pressed for the assembler's name, he'll give it — one person in this city builds nimblewrights, and he knows who.]`

---

## Full example — Location

> *Copper Street works for a living. The tanner next door is already pungent by mid-morning; the candle-maker on the other side has its shutters propped wide. Wedged between them is a narrow building with no sign — painted blue in a shade that was once bright and is now merely insistent.*

`[DM: The blue door is Ott's workshop. The clicking sound audible from outside is a mechanism being calibrated — it stops when they knock. No one else is inside.]`

---

## Full example — Roll result

After a successful Perception check:

> *There — a second figure in the doorway across the street. They haven't moved. They're watching.*

`[DM: Perception DC 14. On a success: the watcher is a Zhentarim tail — they've been following since the party left the Yawning Portal. On a failure: the party doesn't notice until the watcher moves.]`

---

## When to use each layer

| Content | Layer |
|---------|-------|
| What the room looks like | Read-aloud |
| What the party smells, hears | Read-aloud |
| NPC dialogue | Read-aloud |
| NPC's real name (if unknown to party) | DM only |
| NPC's hidden motive | DM only |
| Faction identity (if unconfirmed) | DM only |
| Roll DC | DM only |
| What triggers a change in NPC attitude | DM only |
| Mechanical effects of a spell or item | DM only |
| What happens if the party fails/succeeds | DM only |
| Consequence suggestions | DM only |

---

## Information Discipline

Claude has access to the full campaign source material. Players only know what their characters have discovered in play. **Never reveal in player-facing output what the party has not yet learned in-fiction.**

This covers: narration read aloud, NPC dialogue, consequence suggestions, session recaps at the table.
It does **not** cover: encounter files, state.md, DM prep notes, anything marked `[DM only]`.

**The rule:** If the party hasn't learned it in-fiction, describe — don't name.

| Situation | Wrong | Right |
|-----------|-------|-------|
| Unfamiliar face | *"Urstul Floxin watches from the shadows"* | *"A large man in dark leather armor watches from the shadows"* |
| Unsigned note | *"It's from Manshoon"* | *"It's signed with a single initial — M"* |
| Faction tattoo | *"A Zhentarim operative"* | *"A man with a black winged-snake tattoo on his neck"* |
| Hidden motive | *"She works for the Xanathar Guild"* | *"She's evasive about who she works for"* |
| Room label in read-aloud | *"He'll see you in X18"* | *"He'll see you in the audience chamber"* + `[DM: X18]` |
| Map notation in read-aloud | *"They came from Q7"* | *"They came from deeper in the sewer"* + `[DM: Q7]` |

Names, faction identities, and hidden connections only enter narration and NPC dialogue after the party has discovered them in play. When in doubt, describe appearance and behaviour — not identity.

---

## Quick check before every response

Before writing any scene or NPC response, ask:
1. **Could I hand this text to a player and it would be fair?** → Read-aloud layer
2. **Does this contain information a character couldn't perceive?** → DM-only layer, in `[DM: brackets]`
3. **Is there any `[DM: ...]` text mixed into the read-aloud prose?** → Fix it — they must never be on the same line
4. **Does this name or identify something the party hasn't learned yet?** → Describe instead — see Information Discipline above
5. **Does this contain a map/room label (X18, Q7, area X3)?** → Replace with a descriptive name — these are DM notation, never in-world language
