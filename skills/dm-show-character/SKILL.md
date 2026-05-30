---
description: Display the current full character sheet for a PC, including HP, spell slots, conditions, and resources.
argument-hint: "[campaign] [character name]"
---

Show character $ARGUMENTS

Parse the arguments: campaign name (first word) and character name (remaining words).

Delegate to the `character-tracker` sub-agent to run:
```
python .claude/scripts/show_character.py <campaign> <character name>
```

Display the full output.
