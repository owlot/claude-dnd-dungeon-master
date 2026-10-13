---
description: Generate a named NPC on the fly — stats, personality, voice, motivation, and secret. Use when the party interacts with an unexpected NPC or the DM needs a quick character.
argument-hint: "[role or description, e.g. 'city guard' or 'suspicious merchant']"
---

Generate an NPC matching: $ARGUMENTS

Reference `.claude/rules/items-and-loot.md` for any trade goods context, and `.claude/dnd-5e-srd/markdown/16 npcs.md` for stat blocks.

## Step 1 — Stats (if combat-relevant)

Pick the closest role from the quick reference table:

| Role | HP | AC | Attack | Damage | Save DC |
|------|----|----|--------|--------|---------|
| Commoner (CR 0) | 4 | 10 | +2 | 1d4 | 10 |
| Guard (CR 1/8) | 11 | 16 | +3 | 1d6+1 | 11 |
| Thug (CR 1/2) | 32 | 11 | +4 | 1d6+2 | 12 |
| Veteran (CR 3) | 58 | 17 | +5 | 2d8+3 | 13 |
| Knight (CR 3) | 52 | 18 | +5 | 2d6+3 | 13 |
| Mage (CR 6) | 40 | 12 | +6 | varies | 15 |

If not combat-relevant, skip stats entirely.

## Step 2 — Generate personality

Roll or choose:

**Demeanor**: Nervous / Gruff / Warm / Suspicious / Arrogant / Weary

**Motivation**: Survival / Greed / Loyalty / Ambition / Revenge / Protection

**Secret**: Criminal past / In debt to dangerous people / Knows something they shouldn't / Not who they claim / Betrayed someone / Dying illness or curse

**Physical quirk**: Missing fingers or ear / Distinctive scar / Nervous tic / Unusual eye color / Limp / Constantly chewing / Speaks with hands / Never makes eye contact

**Voice**: Pick one distinctive speech pattern (slow and careful / fast talker / whispers / laughs inappropriately / elaborate vocabulary / heavy accent / stutters when nervous)

## Step 3 — Assign a name

Pick from the appropriate name bank or invent one:

- **Human male**: Aldric, Bram, Cedric, Dorian, Edmund, Felix, Gareth, Hugo
- **Human female**: Alena, Brynn, Cordelia, Delia, Elena, Freya, Greta, Helena
- **Dwarf**: Thorin, Balin, Dagna, Helga, Rurik, Agna
- **Elf**: Aelindra, Caelum, Faelyn, Lirael, Thaelar, Virelle
- **Halfling**: Cade, Eldon, Lidda, Merric, Seraphina, Wellby

## Step 4 — Output

Print the NPC in this format:

```
## [Name]
Role: [occupation]     CR/Role: [if combat-relevant]

Appearance: [one sentence]
Demeanor:   [trait]
Motivation: [what they want]
Secret:     [hidden truth]
Voice:      [how they speak]

Groups:     [tags from `.claude/rules/npc-file-format.md`: local, trade, authorities, criminal, faction:<slug> ...]
Known by:   [who in the setting knows them: usually "only those who deal with them (neighbours, customers, colleagues)"; name wider fame only if the DM wants it]
Stats: AC [X]  HP [X]  Attack +[X] for [damage]   (omit if non-combat)
```

Then ask: *"Do you want me to save this NPC to `campaigns/[campaign]/info/npcs/[name].md`?"* When saving, write the full unified NPC file (`## character`, `## voice`, `## who knows them`, `## background`, `## stats` as needed) following `.claude/rules/npc-file-format.md`: the `Groups` line becomes `groups:` in `## character` and the `Known by` line becomes the tagged `## who knows them` section, so the NPC agents never have to invent who recognises this person.
