---
description: Parse all source files in campaigns/[name]/sources/ and shard them into the campaign directory structure — encounters, characters, locations, and state. Run once before the first session.
argument-hint: "[campaign name]"
---

Index campaign $ARGUMENTS

Delegate to the `indexer` sub-agent to read all files in `campaigns/[name]/sources/` and produce:
- One file per encounter → `campaigns/[name]/info/encounters/[slug].md`
- One file per PC → `campaigns/[name]/party/characters/[name].md`
- Key NPC files → `campaigns/[name]/info/npcs/[name].md`
- One file per location → `campaigns/[name]/info/locations/[slug].md`
- `campaigns/[name]/party/state.md` initialized from the source

After indexing, output a full manifest of every file created and flag any `[DM: verify]` fields that need attention before the first session.
