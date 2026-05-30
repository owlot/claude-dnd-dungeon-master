---
description: Walk through a level-up for a single character — new features, HP roll, spell choices, ASI/feat. Updates the character file.
argument-hint: "[character name] [campaign]"
---

Level up $ARGUMENTS

Parse the arguments: character name and campaign.

## Step 1 — Load current character

Run `python .claude/scripts/show_character.py <campaign> <name>` and display the output.

Note the character's current level, class, and subclass.

## Step 2 — New level

State: *"[Name] is leveling up from [N] to [N+1]."*

Delegate to the `srd-lookup` agent with `class feature: [feature name]` for each feature gained at the new level. Look up features one at a time as needed — do not load the full classes file.

## Step 3 — HP

Ask: *"[Player]: roll your hit die (d[X]) and add your CON modifier ([+N]). What did you roll total?"*

Wait for the result. Update max HP:
```
python .claude/scripts/update_character.py <campaign> <name> hp <new_max>
```

Also update the HP Maximum field in the character file directly (since the script sets Current HP, not maximum — note this and update the `HP Maximum` field manually in the file).

## Step 4 — Class features

List every feature gained at this level. For each feature:
- State the feature name and a one-sentence description
- If it has a limited use resource (e.g., "Channel Divinity (1/rest)"), add it to the Features & Traits section in the character file using the `(X/Y uses)` format the scripts expect
- If it's a passive feature, note it under Features & Traits

Do NOT ask the DM about features that are automatic — just apply them.

## Step 5 — Choices (if any at this level)

Ask only about choices the character actually has at this level:

- **Ability Score Improvement (levels 4, 8, 12, 16, 19):** Ask *"+2 to one stat, +1/+1 to two stats, or a feat?"* then apply.
- **Spellcasting classes:** Ask which new spells are known or added to spellbook. Update spell slots table.
- **Subclass choice (level 3 for most classes):** Ask which subclass. Note features gained.
- **Fighting Style, Expertise, etc.:** Ask the relevant choice.

## Step 6 — Proficiency bonus

If the new level crosses a proficiency bonus threshold (levels 5, 9, 13, 17), note: *"Proficiency bonus increases to +[N]. This affects attack bonuses, save DCs, and all proficient skill checks — update these on the character sheet."*

## Step 7 — Update character file

Write all changes to `campaigns/[campaign]/party/characters/[name].md`.

Confirm: *"[Name] is now level [N+1]. Updated: HP max, features, [spells if applicable]. Review the file for any `[player: confirm]` items."*
