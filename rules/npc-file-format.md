# NPC file format

Every NPC the NPC agents may play has `campaigns/[name]/info/npcs/[slug].md`. Written by the `indexer` (campaign index) and by `/dm-generate-npc` (on the fly); read by the `conversation-npc` agent and, for recognition questions, by the main thread.

## Sections

| Section | Required | Content |
|---------|----------|---------|
| `## character` | yes | key-value schema parsed by the voice tools (`name`, `slug`, `gender`, `age`, `type`, plus role/faction/disposition) followed by a short physical description |
| `## voice` | yes | key-value schema (`pitch`, `pace`, `tone`, `quality`, `notes`, optional `instruction`) followed by the first-person introduction (see `.claude/agents/indexer.md`, step 5) |
| `groups:` (inside `## character`) | **yes** | the groups this NPC belongs to, from the tag vocabulary below (`groups: none` for creatures and objects) |
| `## who knows them` | **yes** (skip only for non-persons with nothing to say) | how well different groups in the setting know this person, so other NPC agents can answer "do I know them?" without inventing |
| `## image` | optional | reference image and appearance |
| `## background` | yes | role, history, secrets, what they would share or withhold, relationships |
| `## behavior`, `## stats`, `## location` | as needed | roleplay triggers, stat block, where they are |

## Tag vocabulary (`groups:` and the bullet tags)

`everyone` (the whole population; implied for every observer, so never listed in `groups:`), `local` (neighbours, regulars, the same street or town), `authorities` (City Watch, magistrates, garrison, officials), `nobles` (noble houses, the Open Lord's circle), `trade` (guilds, merchants, craftspeople, innkeepers), `adventurers`, `arcane` (mages, academies, scholars), `clergy`, `criminal` (crime factions in general), `faction:<slug>` (one organisation, slugified from its name: "Xanathar Guild" becomes `faction:xanathar-guild`; keep slugs identical across files), `party`, and `secret` (what no listed group knows; never passed to an NPC agent). The same tags appear in `groups:` lines and in the bullets of `## who knows them`; the script matches them.

## `## who knows them`

Insert before `## image` if present, else before `## background`. One purpose line, then 3–5 bullets, each starting with the tags of the groups it describes in square brackets, from widest to narrowest knowledge:

- `[everyone]` what the whole population knows (title, landmark, reputation), and whether they know the name or the face
- `[authorities, nobles]`, `[local, trade]`, `[criminal, faction:zhentarim]` and so on: each group at the level it would plausibly know
- `[faction:<slug>]` what the NPC's own organisation knows
- `[secret]` what stays hidden from everyone listed (identities, true allegiance, true nature); this file is DM-side, so naming the secret is fine
- Optionally who in the party's circle has met them (only if the file or the logs say so)

Rules:
- Ground every bullet in the NPC's role, faction, location and background, or in published lore for established characters (famous people and institutions). Never invent history or notoriety.
- A minor or local NPC is known only to those who deal with them (customers, neighbours, colleagues), not to the wider city.
- Secret identities, villains and hidden factions: describe the public picture, then say what stays secret.
- Creatures and objects: say who knows of them and how, or omit the section.
- Update it when the story changes who knows them (a reveal, a death, a public deed).

Used by: `npc_links.py [campaign] [observer-slug] --scene "[DM input]"` (or `--people [slug,...]`) finds every other NPC named in the text and prints, for each, only the bullets that apply to the observer: `[everyone]` plus any whose tags overlap the observer's `groups:`. That output is pasted into `Linked facts`. `npc_links.py [campaign] --audit` lists NPC files that lack the section.
