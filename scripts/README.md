# DM Assistant Scripts

Python 3 scripts for the Claude Dungeon Master system. All scripts use stdlib only — no pip dependencies. Run from the repository root or from any directory (paths resolve relative to the script location).

---

## combat_status.py

Manages and displays the current combat state as a fixed-width box. Called by Claude during combat to produce output that always looks identical.

**Inputs:** `campaigns/<campaign>/combat_state.json` (created by `--init`)

### Usage

```
# Initialize combat from an encounter file (prompts for player initiative)
python scripts/combat_status.py <campaign> --init <encounter_name>

# Display current combat state
python scripts/combat_status.py <campaign> <encounter_name>

# Apply a JSON patch and display updated state
python scripts/combat_status.py <campaign> --update '<json_patch>'
```

### Patch examples

```bash
# Update HP
python scripts/combat_status.py thornwood --update '{"name": "Goblin A", "hp_current": 5}'

# Set conditions
python scripts/combat_status.py thornwood --update '{"name": "Raven", "conditions": ["Poisoned"]}'

# Record death save
python scripts/combat_status.py thornwood --update '{"name": "Marcus", "death_saves": {"successes": 1, "failures": 0}}'

# Advance to next living combatant's turn
python scripts/combat_status.py thornwood --update '{"advance_turn": true}'

# Manually set round number
python scripts/combat_status.py thornwood --update '{"round": 3}'
```

### combat_state.json structure

Created fresh at the start of each combat. Hand-edit or patch via `--update`.

```json
{
  "campaign": "thornwood",
  "encounter": "mill_ambush",
  "round": 1,
  "active_index": 0,
  "combatants": [
    {
      "name": "Raven",
      "type": "pc",
      "initiative": 17,
      "hp_current": 32,
      "hp_max": 45,
      "ac": 15,
      "conditions": [],
      "death_saves": {"successes": 0, "failures": 0}
    }
  ]
}
```

### Output example

```
╔══════════════════════════════════════════════════════╗
║  COMBAT — Round 2                                    ║
╠══════════════════════════════════════════════════════╣
║  INITIATIVE  NAME              HP        AC  STATUS  ║
║  ──────────────────────────────────────────────────  ║
║  ► [17] Raven (PC)            32/45      15  —       ║
║    [15] Goblin Boss (Enemy)   14/30      13  Frightened ║
║    [12] Marcus (PC)           38/38      16  —       ║
║    [8]  Goblin A (Enemy)       0/7       12  DEAD    ║
╚══════════════════════════════════════════════════════╝
```

---

## load_encounter.py

Reads an encounter markdown file and prints a clean, structured DM reference. Use at the start of any encounter to get a quick overview without scrolling through raw markdown.

**Inputs:** `campaigns/<campaign>/encounters/<encounter_name>.md`

### Usage

```bash
python scripts/load_encounter.py <campaign> <encounter_name>
```

### Example

```bash
python scripts/load_encounter.py thornwood mill_ambush
```

### Output sections (always in this order)

1. **ENCOUNTER** — name, location, trigger, type, difficulty, level
2. **READ ALOUD** — boxed atmospheric text to read at encounter start
3. **ENEMY STAT BLOCKS** — HP, AC, speed, initiative, attacks, special abilities
4. **TERRAIN** — feature table with mechanical effects, lighting, map notes
5. **TACTICS** — opening move, priority targets, bloodied behavior, morale
6. **REWARDS** — loot table, XP breakdown, per-character XP

---

## party_status.py

Parses all character sheets and displays a consolidated party overview: HP, AC, conditions, spell slots, and class feature uses.

**Inputs:** `campaigns/<campaign>/characters/*.md`

### Usage

```bash
python scripts/party_status.py <campaign>
```

### Example

```bash
python scripts/party_status.py thornwood
```

### Output example

```
╔══════════════════════════════════════════════════════╗
║  PARTY STATUS                                        ║
╠══════════════════════════════════════════════════════╣
║  NAME           HP         AC   CONDITIONS           ║
║  ──────────────────────────────────────────────────  ║
║  Raven          32/45      15   —                    ║
║  Marcus         38/38      16   Poisoned             ║
╠══════════════════════════════════════════════════════╣
║  RESOURCES                                           ║
║  Raven:       1st: 3/4  2nd: 1/2                    ║
║  Marcus:      Action Surge: 1/1  Second Wind: 0/1   ║
╚══════════════════════════════════════════════════════╝
```

### What is parsed from character files

| Field | Source in character sheet |
|-------|--------------------------|
| HP current / max | `Combat Stats` table rows `Current HP` and `HP Maximum` |
| Armor Class | `Combat Stats` table row `Armor Class` |
| Conditions | Free text in `Notes` section matching `Conditions: ...` |
| Spell slots | `Spell Slots` table — `Total` and `Remaining` columns |
| Class features | Any `**Feature Name (X/Y uses)**` pattern in the file |

---

## update_character.py

Updates a single character sheet in-place with one patch command. Edits the markdown file directly — finds the relevant table row or pattern and replaces the value. Prints a one-line confirmation after every successful update.

**Inputs:** `campaigns/<campaign>/characters/<character>.md`

### Usage

```bash
python scripts/update_character.py <campaign> <character_name> <patch_type> [value]
```

Character name matching: tries exact filename first (lowercased, spaces→underscores), then partial match against filename stem or `# Heading` inside the file. Lists matches and exits if ambiguous.

### Patch types

**HP changes**

```bash
python scripts/update_character.py thornwood raven hp 32        # set Current HP
python scripts/update_character.py thornwood raven damage 8     # subtract from Current HP
python scripts/update_character.py thornwood raven heal 5       # add to Current HP (capped)
python scripts/update_character.py thornwood raven temp_hp 10   # set Temporary HP
```

**Death saves**

```bash
python scripts/update_character.py thornwood raven death_success  # +1 success (at 3: STABLE)
python scripts/update_character.py thornwood raven death_fail     # +1 failure (at 3: CHARACTER DEAD)
python scripts/update_character.py thornwood raven death_reset    # reset both to 0
```

**Spell slots**

```bash
python scripts/update_character.py thornwood raven slot_use 2        # use a 2nd-level slot
python scripts/update_character.py thornwood raven slot_restore 1    # restore one 1st-level slot
python scripts/update_character.py thornwood raven slots_restore_all # long rest: all slots full
```

**Class features / resources**

```bash
python scripts/update_character.py thornwood marcus "feature_use" "Action Surge"
python scripts/update_character.py thornwood marcus "feature_restore" "Second Wind"
python scripts/update_character.py thornwood marcus features_restore_all
```

**Conditions**

```bash
python scripts/update_character.py thornwood raven condition_add Poisoned
python scripts/update_character.py thornwood raven condition_remove Poisoned
python scripts/update_character.py thornwood raven condition_clear
```

**Gold**

```bash
python scripts/update_character.py thornwood raven gold 100       # set gold
python scripts/update_character.py thornwood raven gold_add 50    # add gold
python scripts/update_character.py thornwood raven gold_spend 25  # spend gold (warns if negative)
```

**Hit dice**

```bash
python scripts/update_character.py thornwood raven hd_use 1        # spend 1 hit die
python scripts/update_character.py thornwood raven hd_restore_all  # long rest: all restored
```

### Output example

```
✓ Raven — Current HP: 32 → 24 (took 8 damage)
✓ Marcus — 2nd level slot used (2/3 remaining)
✓ Lyra — Poisoned condition added
```

---

## show_character.py

Prints a clean, readable character sheet for one character in the same box style as the other scripts.

**Inputs:** `campaigns/<campaign>/characters/<character>.md`

### Usage

```bash
python scripts/show_character.py <campaign> <character_name>
```

Same character name matching as `update_character.py`.

### Output example

```
╔══════════════════════════════════════════════════════╗
║  RAVEN — Wood Elf Ranger 3                           ║
║  Player: Sarah                                       ║
╠══════════════════════════════════════════════════════╣
║  COMBAT                                              ║
║  HP: 32/45 (Temp: 0)   AC: 15   Speed: 35 ft        ║
║  Initiative: +3   Hit Dice: 3d10 (remaining: 2)      ║
║  Death Saves: ●●○ / ○○○                              ║
╠══════════════════════════════════════════════════════╣
║  ABILITY SCORES                                      ║
║  STR  DEX  CON  INT  WIS  CHA                        ║
║   10   16   14   12   14   10                        ║
║  (+0) (+3) (+2) (+1) (+2) (+0)                       ║
╠══════════════════════════════════════════════════════╣
║  SAVING THROWS (proficient marked with *)            ║
║  STR +0   DEX +5*  CON +2                            ║
║  INT +1   WIS +4*  CHA +0                            ║
╠══════════════════════════════════════════════════════╣
║  SKILLS (proficient *)                               ║
║  Perception +4*          Stealth +5*                 ║
║  Survival +4*            Nature +3*                  ║
╠══════════════════════════════════════════════════════╣
║  ATTACKS                                             ║
║  Shortsword        +5    1d6+3      Piercing         ║
║  Longbow           +5    1d8+3      Piercing         ║
╠══════════════════════════════════════════════════════╣
║  SPELLCASTING (WIS — DC 13 — +5 to hit)             ║
║  Slots: 1st 3/4  2nd 1/2                            ║
║  Cantrips: Druidcraft, Guidance                      ║
╠══════════════════════════════════════════════════════╣
║  RESOURCES                                           ║
║  Action Surge: 1/1                                   ║
╠══════════════════════════════════════════════════════╣
║  CONDITIONS                                          ║
║  None                                                ║
╠══════════════════════════════════════════════════════╣
║  INVENTORY                                           ║
║  Gold: 45 gp                                         ║
║  Leather Armor (AC 11), Shortsword, Longbow, ...     ║
╚══════════════════════════════════════════════════════╝
```

### What is parsed from character files

| Section | Source in character sheet |
|---------|--------------------------|
| Header | First `# Heading`, top info table (Player, Race, Class, Level) |
| Combat | `Combat Stats` table: Current HP, HP Maximum, Temporary HP, Armor Class, Speed, Initiative Modifier, Hit Dice, Death Saves |
| Ability Scores | `Ability Scores` table — all 6 stats |
| Saving Throws | `Saving Throws` table — modifier and proficiency |
| Skills | `Skills` table — proficient/expertise skills + Perception always shown |
| Attacks | `Attacks` table |
| Spellcasting | `Spellcasting` info table, `### Spell Slots` table, `### Cantrips`, `### Known / Prepared Spells` |
| Resources | Any `**Feature Name (X/Y uses)**` pattern |
| Conditions | `Conditions: ...` line in Notes section |
| Inventory | `### Worn / Wielded` list, `### Backpack` table, `Gold (gp)` from Currency table |

---

## Workflow integration for Claude

During a session, Claude calls these scripts to produce consistent output:

```
# At session start
python scripts/party_status.py <campaign>

# Inspect a single character in full detail
python scripts/show_character.py <campaign> raven

# When combat begins
python scripts/combat_status.py <campaign> --init <encounter>
python scripts/load_encounter.py <campaign> <encounter>

# Each turn
python scripts/combat_status.py <campaign> --update '{"advance_turn": true}'

# After taking damage — update both the combat tracker AND the character sheet
python scripts/combat_status.py <campaign> --update '{"name": "Raven", "hp_current": 24}'
python scripts/update_character.py <campaign> raven damage 8

# After combat: restore resources, clear conditions, update HP
python scripts/update_character.py <campaign> raven hp 45
python scripts/update_character.py <campaign> raven condition_clear
python scripts/update_character.py <campaign> raven slots_restore_all
python scripts/update_character.py <campaign> raven features_restore_all

# After combat ends
python scripts/party_status.py <campaign>
```
