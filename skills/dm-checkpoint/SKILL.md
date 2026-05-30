---
description: Snapshot all character files and combat state mid-session so you can roll back if something goes wrong. Creates timestamped backups in campaigns/[campaign]/.checkpoints/.
argument-hint: "[campaign]"
---

Checkpoint $ARGUMENTS

Run:
```
python .claude/scripts/checkpoint.py $ARGUMENTS
```

Display the full output, which lists every file backed up and the checkpoint timestamp.

Use `/dm-undo $ARGUMENTS` to restore from the most recent checkpoint.
