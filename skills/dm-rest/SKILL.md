---
description: Walk through a short or long rest for one or more characters — hit dice rolls, HP recovery, feature restoration, spell slot recovery. Updates all character files.
argument-hint: "[short|long] [campaign] [character(s) or 'all']"
---

Rest $ARGUMENTS

Parse the arguments first: rest type (short or long, first word), campaign name (second word), and which characters are resting (remaining words; defaults to all PCs if not specified).

Invoke `/dm-checkpoint-log <campaign>` to flush the conversation log. Wait for confirmation, then proceed.

Delegate to the `character-tracker` sub-agent with the following instructions:

## Short rest

1. Ask: *"Which characters are taking the short rest?"* (if not specified in arguments)
2. For each resting character, run `python .claude/scripts/show_character.py <campaign> <name>` to get current HP and hit dice remaining.
3. For each character, ask: *"[Name] has [N]d[X] hit dice remaining and is at [HP]/[max] HP. How many hit dice does [player] want to spend?"*
4. For each hit die spent: prompt *"Roll 1d[X] + [CON mod] — what did [player] roll?"* then run `python .claude/scripts/update_character.py <campaign> <name> heal <result>` and `hd_use 1`.
5. Restore short-rest features. For each character, restore these if present (check the character file):
   - Warlock: all Pact Magic slots → `slots_restore_all`
   - Bardic Inspiration (College of Lore level 5+): restore uses → `feature_restore "Bardic Inspiration"`
   - Ki points: restore all → `feature_restore "Ki"`
   - Superiority Dice: restore all → `feature_restore "Superiority"`
   - Second Wind: restore → `feature_restore "Second Wind"`
   - Action Surge: restore → `feature_restore "Action Surge"`
6. Ask: *"Did anyone use any potions or other items during the rest?"* Update accordingly.
7. Print updated HP bar for each character: `[Name]: ████████░░ 32/45`

## Long rest

1. Ask: *"Which characters are taking the long rest?"* (if not specified)
2. Ask: *"Any interruptions to the rest? (monsters, watches, etc.)"* — if yes, it may not qualify as a full long rest; confirm with DM.
3. For each resting character:
   - Restore HP to maximum: `python .claude/scripts/update_character.py <campaign> <name> hp <max>`
   - Restore all spell slots: `slots_restore_all`
   - Restore all features: `features_restore_all`
   - Restore hit dice (up to half total, rounded down): `hd_restore_all` (note: SRD says you regain up to half your total hit dice on a long rest — ask DM if they track this strictly or restore all)
4. Ask: *"Did the in-game date change? How many hours passed?"* — note for state.md if session is still active.
5. Ask: *"Did anyone level up during the downtime?"* — if yes, trigger `/dm-level-up` for that character.
6. Print a summary table:

```
LONG REST COMPLETE
──────────────────
[Name]    HP: 45/45  Slots: restored  Features: restored
[Name]    HP: 38/38  Slots: restored  Features: restored
```
