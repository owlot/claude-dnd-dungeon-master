---
description: Restore all character files and combat state from the most recent checkpoint. Use after a mistake to roll back to the last /checkpoint save.
argument-hint: "[campaign]"
---

Undo $ARGUMENTS

Run:
```
python .claude/scripts/checkpoint.py $ARGUMENTS --restore
```

Display the full output, which lists every file restored and the checkpoint it was restored from.

If no checkpoint exists, the script will report an error — use `/dm-checkpoint [campaign]` first to create one.
