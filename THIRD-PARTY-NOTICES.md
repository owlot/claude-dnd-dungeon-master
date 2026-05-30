# Third-Party Notices

This repository bundles or builds upon work from third parties. The MIT license
in `LICENSE` covers only the original work authored by the copyright holder. The
components below are governed by their own terms.

## Base project: claude-dungeon-master (PinchOfData)

This project was built as an extension of
[claude-dungeon-master](https://github.com/PinchOfData/claude-dungeon-master) by
PinchOfData. The original DM persona, the core combat/NPC instruction set, and
the bundled 5e rulebook originated there; everything beyond that was added on
top.

**Note on licensing:** at the time of writing, the upstream repository carries
**no explicit license file**, which under default copyright means all rights are
reserved by its author. It is credited here as the starting point for this work.
The MIT license in this repository applies only to the additions and original
code authored by the copyright holder, not to any material derived from the
upstream project. If you intend to reuse or redistribute, please check the
upstream repository's current license status.

## ai-image-creator skill (centminmod)

The `skills/ai-image-creator/` skill is from
[centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup),
used under the MIT License:

```
MIT License

Copyright (c) 2025 George Liu (eva2000)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
```

The `scene-image-generator` agent that drives the skill, and the
project-specific prompt rules, are original work covered by this repository's
MIT license.

## D&D 5e System Reference Document

The contents of `dnd-5e-srd/` are provided under the Open Gaming License v1.0a.
See `dnd-5e-srd/LICENSE` for the full terms.

- Original content: Wizards of the Coast, Inc.
- Markdown/JSON conversion: [Ben Morton](https://github.com/BTMorton/dnd-5e-srd)
  (MIT License, 2017)

Dungeons & Dragons and related names are trademarks of Wizards of the Coast.
This project is an unofficial, non-commercial fan tool and is not affiliated
with or endorsed by Wizards of the Coast.
