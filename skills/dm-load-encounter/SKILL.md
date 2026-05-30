---
description: Verify and display the full encounter block for a named encounter, then prepare for combat. Always cross-checks stat blocks against the SRD before displaying.
argument-hint: "[encounter name]"
---

Load encounter $ARGUMENTS

First, delegate to the `encounter-verifier` sub-agent to:
1. Check the encounter file at `campaigns/[campaign]/info/encounters/[slug].md` for completeness (no missing fields, no `[DM: verify]` placeholders)
2. Cross-check all enemy stats against `.claude/dnd-5e-srd/markdown/11 monsters.md`
3. Report any discrepancies and ask the DM to confirm before proceeding

If the verifier gives the all-clear (or DM confirms to proceed despite issues), delegate to the `combat-tracker` sub-agent to:
1. Display the full verified encounter stat block
2. Prompt for surprise check
3. Collect initiative rolls and begin combat
