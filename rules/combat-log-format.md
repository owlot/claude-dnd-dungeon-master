# Combat Log Format

Reference for both the `combat-tracker` agent (end-of-combat) and the `/dm-combat-log` skill (retroactive from context).

---

## File location

`campaigns/[name]/party/session-[N]/session-[N]-combat-[slug].md`

Where:
- `[name]` = exact campaign folder name (e.g. `waterdeep-dragon-heist`)
- `[N]` = session number from `party/state.md`
- `[slug]` = encounter file name (e.g. `goblin-ambush`)

If `campaigns/[name]/party/session-[N]/` does not exist, stop and report: *"Campaign session folder not found: campaigns/[name]/party/session-[N]/. Check the campaign name and session number and try again."* Do not create the directory.

---

## Format

```markdown
# Combat Log: [Encounter Name] — Session [N]

**Encounter**: [Encounter Name]
**Date**: [real-world date]
**Session**: [N]
**Outcome**: [Victory / Retreat / TPK] — [one-line result]
**XP Awarded**: [total XP or "Milestone leveling — XP not tracked"]

---

## Combatants

| Name | Side | HP | AC | Notes |
|------|------|----|----|-------|
| [PC name] | PC | [max]/[max] | [AC] | [class/level, notable equipment] |
| [Enemy name] | Enemy | [max]/[max] | [AC] | [notable trait] |

---

## Setup

[One paragraph describing the scene, positioning, and any pre-initiative actions (e.g. surprise kills, stealth approach). Include any Stealth/Perception rolls that determined awareness.]

**Surprise**: [none / one side surprised — who and why]

---

## Initiative

| Roll | Name |
|------|------|
| [N] | [Name] |
| [N] | [Name] |

---

## Round 1

**► [Name]** — [Action]: **[roll]** vs AC [N] — **[Hit/Miss]**. [Damage if hit]: **[N] [type] damage**. *[Target] at [HP]/[max] HP.*

**► [Name]** — [Spell/ability]: [effect]. [Save DC if any, result]. *[Condition applied if any.]*

**► [Enemy]** — [Attack] at [target]: **[roll]** vs AC [N] — **[Hit/Miss]**. Damage: **[N]**. *[Target] at [HP]/[max] HP.*

---

*Combat Status — End of Round 1*

    == COMBAT: Round 1 ==
    INITIATIVE        HP          AC   STATUS
    ─────────────────────────────────────────
      [Name] (PC)     [cur]/[max]  [AC]  [conditions or —]
    ► [Name] (Enemy)  [cur]/[max]  [AC]  [conditions or —]

---

## Round 2
...

---

## Combat Over

[Final state — who is standing, who is down.]

---

## Resources Expended

| Character | Resource | Detail |
|-----------|----------|--------|
| [Name] | [spell slot / ability / potion] | [when used and effect] |

---

## Key Moments

1. [Notable moment — nat 20, clutch save, tactical decision]
2. ...

---

## Final Party Status

| Name | HP | Spell Slots | Resources |
|------|----|-------------|-----------|
| [Name] | [cur]/[max] | [slots remaining] | [abilities used] |
```


---

## Formatting rules

- Use `**► [Name]**` to mark the active combatant for each turn
- Write rolls in bold: `**17**`, `**nat 20**`
- Track HP inline after every hit: `*Zemk at 15/26 HP.*`
- Render a Combat Status Block after each complete round (not after every turn) — copy verbatim from the combat tracker output
- If a turn had no meaningful action (surprised, downed, skipped), note it in one line
- If a PC uses an Opportunity Attack during another's turn, record it inline under the triggering turn
- Do not summarize rounds — every turn gets its own line
- Where detail is missing or unclear, write `[unclear from log]` — never invent or infer values
- **Correct spelling mistakes and proper name typos** — use canonical spellings in the log (e.g. "Caelith Morn" not "Caelith Moorn", "Torm" not "Torn"). The DM types quickly; the log should be clean.

---

## XP section

| Source | XP |
|--------|----|
| [Enemy] (CR [N]) | [XP] |
| **Total** | **[XP]** |
| **Per character** | **[XP]** |

If the campaign uses milestone leveling, write: `Milestone leveling — XP not tracked from Session [N] onward.`
