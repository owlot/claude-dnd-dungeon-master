---
description: Distribute loot from the last encounter — prompts who takes what, handles currency splitting, tracks magic item attunement, and updates all character files.
argument-hint: "[campaign] [encounter name or 'manual']"
---

Loot $ARGUMENTS

Parse the arguments: campaign name, and optionally the encounter name to pull the reward table from.

## Step 1 — Load the loot

If an encounter name was given, read `campaigns/[campaign]/info/encounters/[slug].md` and extract the `## Rewards` section.

Display the loot:
```
LOOT — [Encounter Name]
─────────────────────────
Currency:   65 gp, 145 sp, 220 cp
Items:      Mithral Chain Mail (B6 wardrobe, DC 15 Perception to find)
Quest:      Butterskull Ranch complete — 100 gp reward from Harbin Wester
```

If called with `manual`, ask the DM: *"What loot did the party find? List items and currency."*

## Step 2 — Currency

If there's currency, ask: *"How do you want to split the [X gp, Y sp, Z cp]?"*

Options to offer:
- **Even split** — divide equally, remainder stays in party fund
- **Party fund** — all goes to shared pool in state.md
- **DM decides** — DM specifies who gets what

For even split: calculate each PC's share (integer division), note remainder.
Update each character's gold: `python .claude/scripts/update_character.py <campaign> <name> gold_add <amount>`

## Step 3 — Items

For each non-currency item:

1. Describe the item briefly.
2. Ask: *"Who takes the [item]?"*
3. If it's a magic item:
   - Check if it requires attunement (reference `.claude/rules/items-and-loot.md` for attunement rules)
   - If yes, ask: *"Does [character] attune to it now or carry it unattuned?"*
   - Note attunement in the character's equipment section
   - Remind DM: a character can only be attuned to 3 magic items at once
4. Add item to the character's equipment list in their character file.

## Step 4 — Quest rewards

If any quest rewards are listed, display them separately:
```
QUEST REWARDS
─────────────
Butterskull Ranch: 100 gp from Harbin Wester (return to Phandalin to collect)
```

These are pending — do not add to character files until collected. Note them in `campaigns/[campaign]/party/state.md` under Open Threads.

## Step 5 — Summary

Print a confirmation of every change made:
```
LOOT DISTRIBUTED
────────────────
Mithral Chain Mail → Thorin (attuned)
65 gp split: Thorin +21 gp, Raven +22 gp, Lira +22 gp
Party fund: +0 gp (no remainder)
Quest reward pending: 100 gp from Harbin Wester
```
