---
description: Run the Combat Positions battle map — open the standalone map, load an encounter's party map and DM map from sources/, place walls, doors and enemies, and sync token positions so the combat tracker can use them.
argument-hint: "[campaign] [setup | load <encounter> | sync | move Name=Cell ...]"
---

Battle map $ARGUMENTS

The map is a standalone web page served by the table-chat server (`.claude/tools/table-chat`, `run.sh`) at `/map/`, with its own database in `campaigns/[campaign]/party/maps/`. The DM opens the DM link given by the MCP tool `map_links` (`/map/?k=<DM key>`), drags tokens, paints walls and doors and reveals fog; the tablet opens the tablet link (`/map/?t=<tablet key>`, or the Map button on the table-chat page) and sees a filtered copy. Claude reads and writes the board with the MCP tools `map_get`, `map_set`, `map_merge`, `map_asset`, `map_links` and the rest of the `map_*` set (the tools load on demand through ToolSearch). The main thread uses them for setup and map loading; the combat-tracker agent has the same tools and reads positions and writes confirmed moves itself during a fight. `map_get` takes an `out` file and `map_set` / `map_merge` a `file` for large documents. `sync` and `move` below are what the tracker does, and they remain as a manual fallback.

Files:
- Page: `.claude/skills/dm-battlemap/combined.html` (built by `build_combined.py` from `battlemap.html` and the city map; served by `map_service.py`)
- Grid overlay for reading a map: `.claude/skills/dm-battlemap/overlay.html`
- Helper: `.claude/scripts/battlemap.py` (`maps`, `size`, `init`, `summary`, `dist`, `move`, `area`, `path`, `reach`; run it with no arguments for the full usage)
- Links: the MCP tool `map_links` (DM and tablet). Database: `campaigns/[campaign]/party/maps/db.json`, images in `party/maps/assets/`
- Local copy of the board: `campaigns/[campaign]/party/battlefield/dm/state.json`

Cells are written like chess squares: column letters then row number, `A1` is the top-left. One square is 5 ft and distance is measured edge to edge. **Diagonals follow the board rule `diag`**: `"alt"` (default; the 1st diagonal costs 5 ft, the 2nd 10 ft, the 3rd 5 ft, and so on, counted across the whole turn via the token's `dpar`) or `"flat"` (every diagonal 5 ft). It applies to movement, to the distances between tokens, and to reach; the DM can switch it in the Board card. Spell areas (spheres, cones, lines) are measured geometrically and ignore it.

## Data model (database docs)

| Doc | Who reads | Content |
|-----|-----------|---------|
| `dm/state` | editors only | the whole board: `cols`, `rows`, `round`, `rev`, `grid`, `img` (party map), `dmImg` (DM map), `terrain` (`"x,y,kind"` strings: wall, door, opendoor, difficult, cover, hazard), `fog` (`"x,y"` squares hidden from players), `tokens`, `summary`, `sid`, `updatedAt` |
| `dm/state` extras | editors only | `active` (id of the token whose turn it is; the tablet lets players move only this one), `lastMove` (`{id, name, from, to, fx, fy, cost, left, round, t}`, written when a move is made on the table; read it with `battlemap.py lastmove`) |
| `dm/overlay` | editors only | temporary highlights for the DM's board: `label`, `boardRev`, `layers` (`reach` with costs, `path`, `area`), `marks` (ringed tokens). Written from `battlemap.py ... --overlay`; cleared by setting empty layers |
| `table/state` | players | filtered copy: no `dmImg`, no hidden tokens, no terrain under fog, no summary |

A token: `{id, name, side: "pc"|"enemy"|"npc", size: 1-4, x, y, down, hid (enemies and allies: hidden from players; party characters: marked as hiding, still visible to players, dashed), speed (ft), moved (ft used this turn), dpar (diagonals walked this turn, odd or even), portrait (asset id of a face image, optional)}` (`x`,`y` are 0-based; A1 = 0,0; `hid` = hidden from players).
A map: `{id, iw, ih, scale, ox, oy}` — `id` is the uploaded asset, `iw`/`ih` its pixel size, the image is `cols × scale` squares wide, shifted `ox`/`oy` squares. Add `"autoalign": true` to make the page detect the printed grid and set `scale`/`ox`/`oy` itself.

**Never write `table/state` by hand** (it is the players' copy; a mistake leaks hidden tokens). Write `dm/state` with `"sid": "claude"`: the open DM page adopts it and then rewrites `table/state` itself. The DM must have the page open for that to happen.

## setup

1. Make sure the table-chat server is running (`.claude/tools/table-chat/run.sh`); `python .claude/tools/table-chat/table_chat.py status` answers when it is.
2. The MCP tool `map_links` gives the DM link and the tablet link. Tell the DM to open the DM link; the tablet gets its link through the Map button of the table chat (or the tablet link directly).
3. Nothing to publish and nothing to share: access follows the two keys (`.dm-token` = DM, `.table-token` = players). To change the page, rebuild `combined.html` (`build_combined.py`) and reload.

## load <encounter>

Loads the map(s) for one encounter, builds the board from the map and the encounter's room descriptions, and hands it to the DM to check. Draft quality depends on how well the map reads, so always present the result as a draft.

1. **Find the maps.** Read `campaigns/[campaign]/info/encounters/[encounter].md` (read-aloud, rooms, enemies, any positioning). Run `python .claude/scripts/battlemap.py maps [campaign] [words from the encounter name, chapter, location]`. The output lists role (`dm` / `player` / `shared`), whether the player map has a printed grid, the size in squares from the file name, and pixels.
   - **Party map** = a `player` file (prefer the `NoGrid` one: the page draws its own grid) or a `shared` file.
   - **DM map** = the `dm` file. Optional; it shows only on the DM's board and is never sent to players.
   - If more than one candidate fits, or none does, ask the DM which file to use. Do not guess between encounters.
2. **Grid size.** When the file name gives `CxR` squares, use them: `cols = C`, `rows = R`, `scale: 1`, `ox: 0`, `oy: 0` (check that `iw / C` is about `ih / R` with `battlemap.py size`; these official maps are exactly C×R squares). When it does not, set `cols` to your best estimate and add `"autoalign": true` to each map.
3. **Register the image(s).** The MCP tool `map_asset` (file: the path of the party map, and again for the DM map): it serves the file without copying it and prints the asset `id`. The file must be inside the campaign folder (`sources/`) or the website's images for the campaign (`website/[campaign]/assets/world-images/...`, e.g. the character portraits); the map stores only a repo-relative path, so `party/maps/` holds just `db.json` and `assets.json`. Use those ids in the map specs.
4. **Read the map.** Start a local file server from the project root in the background: `python3 -m http.server 8765 --bind 127.0.0.1`. Open the overlay in the Browser pane in bands of about ten rows, full width, so each square is legible:
   `http://127.0.0.1:8765/.claude/skills/dm-battlemap/overlay.html?img=/campaigns/[campaign]/sources/[path to the DM map or, failing that, the party map]&cols=C&rows=R&scale=S&ox=X&oy=Y&r0=1&r1=10` (then `r0=11&r1=20`, and so on; URL-encode spaces and brackets). Screenshot each band and read the cell labels. Stop the server when done (`pkill -f "[h]ttp.server 8765"`).
5. **Write a spec** and build the board with `python .claude/scripts/battlemap.py init [campaign] spec.json` (spec file in the scratchpad):
   ```json
   {"cols": 22, "rows": 30,
    "img": {"id": "…", "iw": 3300, "ih": 4500, "scale": 1, "ox": 0, "oy": 0},
    "dmImg": {"id": "…", "iw": 3300, "ih": 4500, "scale": 1, "ox": 0, "oy": 0},
    "walls": ["B2:H2", "B8:H8", "B2:B8", "H2:H8"], "doors": ["H5"], "opendoors": [],
    "difficult": ["G6:H6"], "cover": [], "hazard": [],
    "tokens": [{"name": "Yagra Stonefist", "side": "pc", "at": "C4", "hid": false},
               {"name": "Duergar", "side": "enemy", "at": "J5", "size": 1}],
    "reveal_rooms_from": ["C4"]}
   ```
   Ranges like `B2:H2` are filled rectangles. Repeated names are numbered automatically. Enemies are hidden from players by default. `fog` defaults to everything hidden; `reveal_rooms_from` floods the starting room(s) up to walls and closed doors.
   Placement rules:
   - **Walls**: mark only the squares that bound the walkable space (an unbroken ring around each room and along corridors), not the solid rock beyond. The ring must be 8-connected so the page's Reveal room tool cannot leak through a gap.
   - **Doors**: one `door` square (closed) or `opendoor` square (open; the read-aloud says when) in each doorway the map or the text shows. Secret doors and traps are DM information: put them in the message to the DM, not on the board, unless the DM asks.
   - **Terrain**: difficult, cover and hazard squares only where the map or the text shows them.
   - **Enemies**: take counts, names and sizes from the encounter file (Large = 2, Huge = 3, Gargantuan = 4). Place them where the encounter text puts them; if it names only a room, put them inside that room at plausible squares and say so. Never add creatures the encounter does not list.
   - **Party**: one `pc` token per character in `campaigns/[campaign]/party/characters/`, at the entrance the party uses (or where the text says they start). Ask the DM if the entrance is unclear.
   - **Speed and portraits**: `python .claude/scripts/battlemap.py roster [campaign]` lists each character with the speed from their sheet (the `Speed` row) and the website portrait file (the sheet's `## image reference:`, else `assets/world-images/npcs/<slug>`). `init` fills each party token's `speed` from the sheet automatically. Portraits need registering: register each portrait file with `map_asset` (one call per file; the file must be inside the campaign folder), put each returned id on its token as `"portrait": "<id>"` in the spec. For a board that already exists, register the portraits, write a small JSON `{ "<portrait file path>": "<asset id>" }`, run `python .claude/scripts/battlemap.py apply-roster [campaign] <that file>`, and send the `push.json` it writes with `map_set` (path dm/state, file the push.json path). Tokens without a portrait show initials. Named NPCs with a website image resolve the same way; enemies from the monster list have none.
6. **Write it.** Read the current board with the MCP tool `map_get` (path `dm/state`): if it holds tokens or fog from a fight in progress, ask the DM before replacing it. Then write the new one with `map_set` (path `dm/state`, file `campaigns/[campaign]/party/battlefield/dm/new_state.json`).
7. **Report to the DM**, briefly: which files were used (party / DM), the grid size, what was placed, and anything uncertain (enemy squares inferred from a room name, doors or walls you were unsure of). Prompt: *"Open the battle map and check the walls, doors and tokens; fix anything with the tools, then say 'sync'."*

## sync

Refresh the local copy so the combat tracker sees current positions. Run it when combat starts, at the start of each round, and whenever the DM says positions changed.

1. The MCP tool `map_get` (path `dm/state`, out `campaigns/[campaign]/party/battlefield/dm/state.json`).
2. `python .claude/scripts/battlemap.py summary [campaign]`. Use that text, or tell the combat-tracker the file is fresh.
3. If the page was never opened or `dm/state` does not exist, say so and ask the DM to place tokens.

## move

When the combat tracker (or the DM) resolves enemy or ally movement, put it on the board:

1. `python .claude/scripts/battlemap.py move [campaign] "Groz=N8" "Bonegnasher 1=O6"` (it checks the grid, warns about walls and overlaps, and writes `battlefield/dm/push.json`).
2. `the MCP tool `map_set` (path `dm/state`, file `campaigns/[campaign]/party/battlefield/dm/push.json`.`) If the DM moved something since your last read, read again first and redo the move.
3. The open DM page adopts the change within a second or two.

Moves are always proposals the DM confirmed at the table; never move a player's token on your own.

## Limits to state when asked

- The map is read by eye from the picture. Expect to correct a few walls, doors or squares; the page's tools make that quick.
- Line of sight and cover are not calculated. Positions, distances, reach and listed terrain are.
- Players get a filtered copy, but the party map image file itself is not protected: fog hides it on screen, not in the file.

## Table moves (players move the active character)

Players move the character whose turn it is, from a tablet or phone at the table. There are two ways to set that up; both end the same way (the move is checked and saved to `dm/state`, with `lastMove`, so the DM's board and the combat tracker see it):

1. **The tablet link** (`/map/?t=<tablet key>`, or the Map button on the table-chat page; no DM key needed). It gets the players' board (fog opaque, nothing hidden shown) and can drag the active character's token or tap a lit square. It only sends a *move request* (database doc `moves/table`); **the DM's own page, open in plain DM view (not table mode), checks the request against the real board** (speed, 5/10/5 diagonals, walls, enemies, difficult terrain, revealed squares, active turn) and applies it or answers with the reason (`table/reply`). So the DM's page must be open. The tablet key can never read `dm/*`. The DM can switch this off with the **"The table tablet can move the active character"** checkbox in the Board card. Requests older than a minute or already handled are ignored.
2. **A tablet on the DM link** in **Table mode** (button in the header, remembered per device). It shows the players' board and applies moves itself. **Leave it by pressing and holding the page title for about a second, tapping the title five times within three seconds, or opening the page with `#dm` on the end** (deliberately hidden from players).

Illegal moves snap back with a message. An **Undo move** button (on the tablet) takes the last move back. The DM starts a turn with the roster's **Turn** button (or the tracker runs `battlemap.py turn`); speed and movement used are editable in the token panel. Other read-only devices see the active marker and lit squares but cannot move anything. Both the DM and players have a per-device **Movement overlay** button that shows or hides the lit squares.

## Spell effects (clouds, moonbeam, traps)

`dm/state.effects` is a list of areas that stay on the board: `{id, name, shape: sphere|cube|cone|line, size (ft: radius, side or length), width (lines), ox, oy (origin in squares; whole numbers are grid crossings, x.5 are square centres), ang (degrees, 0 = east, clockwise on screen), owner (caster token id), follow (centred on the caster), rounds (left, null = no limit), conc, kind (damage|obscure|dark|terrain|utility), note, by (dm|player|claude), hidden}`. Presets (shape, size, duration, rules note) are in `.claude/skills/dm-battlemap/spell-effects.json`, checked against the SRD with `srd_lookup.py`; anything not in the SRD (cloud of daggers) is marked for the DM to verify.

**The rule for which squares are hit**: a square is affected when its **centre** is inside the shape or on its edge. A 5 ft cube or 5 ft radius whose origin is on a grid **crossing** therefore covers the 4 squares around it; on a square centre a cube covers that one square and a 5 ft radius covers it plus its 4 neighbours. Cones and lines start at the caster. A creature is affected if any of its squares is.

**Placing**: the **Spells** button (DM view, Table mode, or a Contributor tablet) opens the preset list and a custom area. After choosing, the board is in placement mode: tap or drag to aim (it snaps to the nearest grid crossing or square centre; the Snap setting can force crossings or centres), the squares that would be hit light up with their count, then **Place**. Cones, lines and caster-centred spells (spirit guardians) start at the caster (the active character on the tablet, the selected token for the DM) and are aimed by dragging. Tablets send a request that the DM's page checks (valid shape, size 5 to 200 ft, a real non-enemy caster, at most 30 areas) and applies; players can remove only spells that players placed. The DM sees a "Hidden from players (a trap)" option; hidden effects are drawn dashed on the DM board and are left out of the players' copy entirely. In the **On the board** list the DM can hide or show an effect, add or remove a round, or remove it.

**Rounds**: the DM's **+** on the round counter, or `battlemap.py turn ... --round N`, counts every effect down and removes expired ones (instant spells such as fireball last one round so the table can see who was hit).

Tracker commands: `effects`, `where`, `effect add|remove|presets`, and `ENTERED`/`LEFT` lines in `lastmove`.

## Zoom and pan

Everyone (the DM, table tablets, read-only viewers) can zoom and pan the board: **pinch with two fingers** (or ctrl + mouse wheel / a trackpad pinch), the **+ / − / Fit** buttons at the top right of the map, and **drag the empty ground with one finger** to pan. On the DM's page, hold **space** while dragging (or use the middle mouse button) to pan so it does not clash with the editing tools. Dragging the active token and tapping a lit square still move it at any zoom. The zoom is per device and is not saved. In the players' view (tablets, read-only viewers, Table mode) the board is **sized to fit the screen**, so the whole map is visible without scrolling the page. When the turn passes to another token the map **recentres on it automatically**, and in the players' view it also **zooms in so squares are at least about 36 px** (so a big map is readable on a tablet; players are never pointed at a token they cannot see). The **Follow** button next to Fit turns this off on that device.

## Free movement (out of combat)

When **no turn is active** (the board's `active` is empty) the table is out of combat: players can move **any party character** any distance, by dragging it or by tapping a character and then a square. Walls, enemies and unrevealed squares still block, no movement is counted, no lit squares are shown, and enemies and allies cannot be moved from the table. It is recorded as `lastMove` with `free: true`; **Undo move** works. The moment a turn starts (the roster's Turn button, or `battlemap.py turn <campaign> "<name>"`) the combat rules apply again (only the active character, within its remaining speed); `battlemap.py turn <campaign> none` ends combat and unlocks the table. The checkbox "The table tablet can move the active character" still switches table moves off entirely.

## Group move (out of combat)

An option for when no turn is active: moving **one** party member moves **all** party members (not "down") by the same step, so the formation stays. It is all or nothing: if anyone would end up in a wall, off the map, on someone else, in unrevealed ground or somewhere they cannot walk to, nobody moves and the message names who is blocked. The DM switches it in the Board card ("Out of combat, the party moves together") and the table tablet (and any Contributor account) has a **Move together: on/off** button, visible during combat too but disabled then, in its bar (visible out of combat only; it sends a request that the DM's page applies). While dragging, outlines show where the rest of the party would land. **Undo move** puts the whole party back. It is recorded as `lastMove` with `free: true` and a `group` list. In combat the option does nothing (only the active character moves). It is off by default.

## Token stats

Each row of the token table shows `AC n · HP cur/max (+temp)` (red at a quarter or less). Click a token's name to open its panel: AC, current/max/temporary HP (editable, the board saves them), ability scores, an attack table (to hit, damage, notes), and traits. These fields are DM-only: they are never copied into the players' `table/state`. Party data comes from the character sheets: `battlemap.py apply-roster [campaign]` (refreshes AC, HP, abilities and attacks, plus speed; give it an assets.json to set portraits too). Enemies and allies: write a JSON file keyed by token name (`{"Kobold 1": {"ac":12,"hp":5,"maxhp":5,"info":{"attacks":[{"n":"Dagger","b":"+4","d":"1d4+2","t":"piercing","note":""}],"traits":["Pack Tactics: ..."]}}}`) from the encounter file and run `battlemap.py apply-stats [campaign] file.json`; push the resulting `push.json` as usual. The combat tracker still owns HP during a fight; keep the panel in step by editing HP there or re-running apply-roster after saving the sheets.

Party tokens: the table can move party characters (side `pc`) and allied companions (side `npc`); out of combat any of them, in combat only the active one.

## Side cards

On the DM page the cards (Tokens, Distances, Map & fog, Snapshot, Board) can be rearranged: drag a card by its heading (the ⠿ grip). Drop it anywhere over the map column to place it in the strip under the map (cards there sit side by side as space allows), or on one of the two bars that appear at the bottom of the screen while dragging ("under the map" / "side column"); drop on another card to reorder. The page scrolls when a card is held near the top or bottom edge. The layout is remembered on that device; double-click any heading to put every card back in the right-hand column.

## Axis labels

The column letters (top) and row numbers (left) stay pinned to the edge of the visible window while you zoom and pan, at a constant readable size, on a slightly opaque strip. A wind rose is pinned to the lower-left corner of the view the same way (constant size, N highlighted); north is up the page, the direction of rows 1, 2, 3 ... counting down is south.

## Start / End combat

The button next to the round counter reads **Start combat** when no combat is running and **End combat** when one is. The board keeps a `combat` flag for this.

- **Start combat** (one tap): sets the flag, round 1, no active turn, movement reset. From then on the table is locked to turns: only the active character can move, and the table bar says "Combat has started: waiting for the first turn" until a turn is set. Press **Turn** on a token (or the tracker runs `battlemap.py turn`) to give the first turn.
- **End combat** (two taps; the first turns the button red, it disarms after 5 seconds): clears the flag, the active turn and the last move, sets the round to 1 and resets every token's movement. The party moves freely again. Spell effects, HP and positions stay. Undo restores it.
- Setting any turn (the Turn button, or `battlemap.py turn <token>`) also switches combat on; `battlemap.py turn none` switches it off.

## Measure mode

The **Measure** button (header, everyone, also on the tablet) turns on measuring: tap two places and the bar shows the distance: the grid distance under the board's diagonal rule (a token snaps to its whole footprint, edge to edge, so it matches `dist`), the straight-line distance, and the walking cost around walls and difficult terrain (creatures ignored; "no walking route" if walls close it off). A dashed yellow line with the feet is drawn on the map, and when the walk differs a green line follows the walking route around the walls (the label then reads `N ft · walk M`). Under fog players cannot pick an unrevealed square. It is local to the screen. **New measurement** starts over, **Done** leaves the mode; dragging still pans.

## DM pan and zoom

On the DM page, dragging empty ground pans (a plain tap on an empty square still moves the selected token there); dragging a margin outside the grid pans; the mouse wheel or a two-finger scroll pans when zoomed in (Shift for sideways); Ctrl + wheel or a pinch zooms; Space + drag, the middle button and two fingers still work; the paint and fog tools keep their own drags.

## The combined "Table Maps" page

The battle map and the city map are two tabs of one page (Battle map | City map). `build_combined.py` builds `combined.html` from `battlemap.html` and `../dm-citymap/citymap.html`: each page runs in its own shadow root with its own `document` stand-in (ids, styles and `body` rules cannot collide; key presses reach only the visible tab; the theme colour tokens are shared from the battle page). The table-chat server serves `combined.html` at `/map/` with `static/map-shim.js`, a small runtime stand-in for the database, user and asset calls the pages make (`window.claude.use("db" | "user" | "assets")`); `map_service.py` stores the documents and enforces the access rules (`dm` DM only; `table` players read, DM write; `moves` both; `city` DM only; `citypub`, `citypins` players read, DM write; `citypins/<own id>` players write). Rebuild with `python3 .claude/skills/dm-battlemap/build_combined.py` after changing either page. The URL `#city` or `#battle` opens a tab directly; the last tab used is remembered per device.
