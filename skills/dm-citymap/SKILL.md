---
description: The zoomable Waterdeep city map page — pins for the party and places, fog the DM reveals, jump buttons to each ward list. Use to show or update the city map for a campaign.
argument-hint: "[campaign] [pin | reveal | status]"
---

City map $ARGUMENTS

A page of the standalone map (served by the table-chat server at `/map/`, a tab next to the battle map; page template: `.claude/skills/dm-citymap/citymap.html`) that shows the city poster `campaigns/[campaign]/sources/Waterdeep-map.jpg` (6000×5200 px: the city in the middle, the ward lists and the structure legend around it). Its links come from the MCP tool `map_links`.

## What it does
- **Zoom and pan** for everyone: pinch, drag, ctrl/plain mouse wheel, the + / − / Fit buttons. The poster is sized to fit the screen.
- **Jump buttons**: Whole poster, City map, each ward list (Sea, Castle, Dock, North, Trades, South, City of the Dead), Deepwater Harbor, Structure legend.
- **Pins** (DM): *Add pin*, then tap the map. Kinds: Party (teal, arrow), Place (amber), Note (blue). Each has a label and a "Visible to players" switch; pins that players cannot see are drawn dashed on the DM's screen and are left out of the players' copy entirely. Drag a pin to move it, tap one to edit or delete it.
- **Fog** (DM): *Fog on* covers the whole poster for players (opaque; translucent for the DM). *Reveal box* / *Hide box* drag a rectangle (150 px cells) to uncover or cover an area. *Reveal all* clears it. The ward lists are on the poster too, so cover or reveal them as you like. Fog starts off.
- **Players' view** button (DM) previews what players see. Anyone on the tablet link gets the players' view, read-only.

## Data (map database, MCP tools `map_get`, `map_set`, `map_merge`)
| Doc | Who reads | Content |
|-----|-----------|---------|
| `city/state` | editors only | `img {id, iw, ih}` (the poster asset), `fogOn`, `revealed` (`"x,y"` cells of 150 px), `pins [{id, label, x, y, kind: party|place|note, pub, desc, loc}]` (x,y in poster pixels; `desc` = text shown when the pin is tapped, `loc` = slug of the known place it was chosen from), `routes [{id, name, pub, pts: [{x, y, l: label, p: pin id}]}]` (saved routes from Measure; listed on the card of their first and last pin), `rev`, `sid`, `updatedAt` |
| `citypub/state` | everyone it is shared with | the same without private pins and without routes that are not `pub` |
| `citypins/<id>` | everyone read; the owner writes | one document per player: `pins` (same fields as above, minus `pub`) and that player's saved `routes` |

The open DM page writes both docs on every change. To change the map from here (for example, drop a "Party" pin): Use the MCP tool `map_set` (path `city/state`; read it first with `map_get`) with the full `pins` list and `sid: "claude"`; the open DM page adopts it but does **not** rebuild `citypub/state` by itself for that, so also write `citypub/state` with only the `pub: true` pins (never copy private pins into it).

## Setup
Setup: the page is served as a tab of the standalone map (see dm-battlemap). Register the poster with the MCP tool `map_asset` (file `campaigns/[campaign]/sources/Waterdeep-map.jpg`), then write `city/state` and `citypub/state` with `map_set`, with `img` = the returned id, `iw` 6000, `ih` 5200. Nothing to share: the tablet link shows the players' view.

## Legend
The **Legend** button in the header (everyone) opens a sheet with a search box (matches `code: name`, case-insensitive, so `T3`, `dripping` or `T3: Inn` all work; Enter picks the first hit), a ward filter and the building list. Tapping an entry closes the sheet, zooms to 6x centred on the building and flashes an amber ring there for 3 seconds (a timed SVG ring, never saved). Entries without a map position zoom to their line in the ward key box instead and say so in a toast. A code printed more than once on the map (for example the C19 guard barracks) shows a ring at every spot and zooms to the first. Players' view (and real players) with fog on: if the target is still covered the page does not zoom and shows "Not revealed yet"; the DM is never restricted. The building names are in the page for everyone, fog or not.

**Data**: `.claude/skills/dm-citymap/legend.json`, one object per entry: `code`, `ward` (sea, castle, dock, north, trades, dead, south, harbor: the poster uses `S` for both the Sea Ward and the South Ward, `ward` tells them apart), `name`, `detail` (the text in brackets), `list` [x, y] (poster px, centre of its line in the ward key box), `pos` [x, y] (poster px, the code label on the city map, or null), `conf` (`high` | `medium` | null), optional `also` (other places the same code is printed). It is inlined into `citymap.html` between `/*LEG:START*/` and `/*LEG:END*/` (the page cannot fetch files).

**Where it came from**: the key lists were transcribed by eye from magnified crops of the poster (`src/<ward>.txt`, names exactly as printed, including the poster's own typos); the labels on the city map were found by cropping the poster (white label boxes detected in a canvas, then read from magnified contact sheets; plain unboxed labels read from 1:1 tiles) and every manual position was checked against a crop. `pos` is the label, which sits on or beside its building (some South Ward labels point to the building with a leader line).

**Coverage** (446 entries): 446 with a list position; 441 with a map position (415 high, 26 medium), 5 without. Medium = the code is printed twice or more on the poster (S33, N32, T31, D70, S48, C19), the South Ward inset labels S28-S48 (an enlarged inset beside the map, not the building's own spot), or S55 (the key prints `S55` between S50 and S52, S51 is missing; the map label `S51` is used). No map label found for C80, C84, D57, D72, H7. Poster oddities kept as printed: C37 has no detail and there is no C38 entry in the key although a `C38` label is on the map; the key entry after C84 reads `CSS` and is stored as C85; C67's floors printed `S` (stored as 5); D53 is stored as `Dwar?s` (unclear letter); T34 detail `G?`; a South Ward map label `S57` matches no key entry. Structure legend (building classes) is not a building list and is not included.

**Add or correct an entry**: edit the ward's `src/<ward>.txt` (key line: `CODE|name|detail`; ` ##2` at the end if the line wraps to two lines; `@col x y pitch` starts a key column) and/or `src/positions.json` (`"ward:CODE": {"pos": [x, y], "conf": "high", "also": [[x, y]]}`), run `python3 .claude/skills/dm-citymap/src/build.py` (rewrites `legend.json` and the data block in `citymap.html`), then rebuild the combined page with `python .claude/skills/dm-battlemap/build_combined.py` and reload `/map/`.

## Tapping the printed ward lists

Besides the Legend panel, the **printed ward lists on the poster are tappable**: zoom into a ward list (the jump buttons do this), tap a building's line, and the map zooms to that building (6x) with a flashing ring. A **Back** button then returns to the list view. It uses each entry's `list` position in `legend.json` (a tap picks the nearest line in the right column, within about 22 poster pixels, so zoom in first: the text is tiny when the whole poster is shown). In the players' view, a building that is under fog does nothing except the toast "Not revealed yet". Note: the labels on the poster's city map print the letter S with a stroke through it, so "S4" looks like "$4"; that is the poster's own artwork.

## Search box

A search box sits in the page header (always visible). Type a code (`T3`) or part of a name (`dripping`, `inn`); up to 8 matches appear (exact code first, then code prefix, name prefix, name contains, ward name). Pick one with a tap, or the arrow keys and Enter (Enter takes the top result), and the map zooms to the building with the ring and a Back button, exactly like the Legend panel. Buildings without a map position zoom to their line in the ward list. Under fog, players get "Not revealed yet" instead of a zoom.

The search also finds **pins**: a pin you place (for example "Trollskull Alley") is searchable by its label, and zooming to it works like a building. Players only find pins marked "Visible to players". The poster's own lists only cover the 446 buildings printed on it, so campaign places that are not on it (Trollskull Alley, Trollskull Manor) need a pin.

## Streets

The header search (and only it; the Legend panel lists buildings) also finds the **street and place names printed on the city map** that are not keyed buildings: `Trollskull`, `Delzorin`, `dock` list matching labels with a small STREET / PLACE / GATE / WATER tag. A name that starts with the query ranks above buildings whose name merely contains it; apostrophes are ignored (`kulzars` finds Kulzar's Alley). Choosing one zooms to 6x on the label with the flashing ring and a Back button, exactly like a building; a name printed in several places (Delzorin Street, The High Road, Saerdoun Street, North Trollwall, Lamp Street, Westwall Street, Diamond Street) rings each place that is not under fog and zooms to the first. Players with fog on get "Not revealed yet" and no zoom when every position is covered; the DM is never restricted.

**Data**: `.claude/skills/dm-citymap/streets.json`, one object per name: `name` (as printed; `?` marks a letter that could not be read), `kind` (street | gate | district | water | landmark | other), `pos` [x, y] (poster px, centre of the label; for a long or curved label its middle), optional `also` (other places the same name is printed), `conf` (high | medium; medium shows "position approximate" in the toast). It is inlined into the page between `/*STR:START*/` and `/*STR:END*/` by `src/build.py`.

**Coverage** (147 names: 125 streets and alleys, 13 places such as Mount Waterdeep, The Market and Virgin's Square, 7 water names, 2 gates; 141 high, 6 medium): the whole city map was scanned in overlapping tiles of about 500x380 poster px at 2x (every tile inside x 1965-4035, y 375-4725 that holds anything but open sea or country), names transcribed from the crops, then every position was checked by drawing a marker on the poster. The ward key lists, building codes and the poster's own title were not indexed. Possible gaps: a label too small, faint or cut by a tile edge may have been missed (the long streets' secondary prints are the likeliest to be missing from `also`), and the ocean names beyond the harbour (printed only on the sea part of the poster) were read at lower zoom. Uncertain readings: Mhalsy?mber's Way and C?mbril's Walk (one letter unclear), Sashtar Street (the label is split in two pieces), Horn Street, Sammarin's Street and Beaconmarch (tiny lettering, medium confidence in the data where marked). "Immar Street" (east) and "Imar Street" (north-centre) are two different printed labels.

**Add or correct a name**: edit `streets.json` (find the label on a crop of the poster, `pos` = its centre in poster pixels; a crop page that draws a 100 px grid makes this quick), run `python3 .claude/skills/dm-citymap/src/build.py`, then rebuild `combined.html` (`python .claude/skills/dm-battlemap/build_combined.py`) and reload the page. Keep other dm-citymap data untouched.

## Player pins

Players with **Contributor** access (the same level the table tablet needs for moves) get an **Add my pin** button in the header: tap it, tap the map, give the pin a label and a kind (Place or Note), and it appears for the whole party and the DM as a **diamond** (with a bold white edge on the pin's owner's own screen). Rules: a player can only drop a pin where the map is revealed (not under fog); at most 20 pins each; a player can edit, move-by-replacing or delete only their own pins; other players' pins are read-only (tapping one shows its label). The DM sees every player pin and can edit or delete any of them. Players' pins are searchable like the DM's pins. Players with view-only access see the diamonds but have no button.

Data: each player has one document `citypins/<their user id>` = `{pins: [{id, label, x, y, kind}], updatedAt}`; rules `citypins` read view, write admin, and `citypins/{self}` write interact, so a player can only ever write their own document. Not private: everyone with view access can read them. (Private notes are not built; they would live under `data/users/<id>/`.)

## Show / hide pins

The **Pins** button in the header (everyone) hides every pin on that screen (the DM's, the players' and the party pin) and shows them again; it reads "Pins hidden" while off. It is remembered per device and only affects what you see: nothing is deleted or changed for anyone else, and a hidden pin cannot be tapped or snapped to by Measure. Opening the pin editor to add or edit a pin turns pins back on.

## Measure mode

The **Measure** button (header, everyone) turns on route measuring: tap a first place, then keep tapping to add waypoints. The bar shows the total and each leg, with a dashed line through all points and a label at the end (`distance · walking time`). A pin snaps to its own spot (its name is used in the text); anywhere else is a plain point. Distance is in feet, plus miles from 1,000 ft up; time is on foot at a normal pace (3 miles an hour, 264 ft a minute; streets wind, so real walks are longer). **Undo point** removes the last waypoint, **New route** starts over, **Done** leaves the mode. Dragging still pans while measuring. The scale comes from the poster's printed 1,000-ft scale bar, about 189.5 poster pixels long (about 5.28 ft per pixel, good to a couple of percent). The route is local to the screen; it is not shared.

## Now a tab of the combined page

The city map is one of two tabs of the **Table Maps** page (the battle map is the other). It is served at `/map/` by the table-chat server. Build it with `python .claude/skills/dm-battlemap/build_combined.py`, which merges `dm-battlemap/battlemap.html` and `dm-citymap/citymap.html` (edit those, never the output `combined.html`); reload the page afterwards.


## Pin editor: known places, descriptions and saved routes

- **Known place dropdown.** The page asks the table-chat server for `GET /map/_places` (capability `claude.use("places")` in `static/map-shim.js`). Players get the places in the website's Places list (`website/<campaign>/world.json` cards, with the text from `world-public.json`, so only what the party knows). The DM also gets the campaign's locations (`info/locations`, `party/locations`) that have no card yet, listed under *Not yet known to the players* with "not known to players" in the option text. Picking one fills the label and description (editable) and sets *Visible to players* on for known places, off for unknown ones (with a hint).
- **Description.** Shown on a card when a pin is tapped (by anyone); a pin with no description of its own shows the known description of the place it is linked to, or of the place with the same name. The DM and the pin's owner get an Edit button on the card.
- **Routes.** In Measure, *Save route* names the route being measured (DM: with a *Visible to players* box, default on only if no end is a hidden pin; players: always shared with the party). The route is listed, with Show and Delete, on the card of the pin it starts or ends at (ends are matched by pin, so the route must start or end on a pin). Show draws the route and zooms to it until *Hide route*.

## Find routes (automatic path finding)

*Find routes* (header) → tap two spots (a pin snaps to its own spot) → *Find* → up to three walking routes, the shortest (by real distance) highlighted in gold, the alternatives cyan and pink, each with distance and walking time (3 mph). Tapping an option highlights it; *Save route* saves the highlighted one exactly like a measured route (name, *Visible to players*, listed on the cards of its first and last pin). *New points* starts over; *Done* leaves the mode.

How it works: `src/build_routing.py` reads the poster once and writes a small walking-cost grid (`routing.png`, 517 x 1087 cells at 1/4 scale: water, parkland and cliffs blocked; wide streets cost 1, narrow lanes 1.6, roofs 5, so routes follow streets and cut through a block only when that saves a lot). The grid is inlined in `citymap.html` between `/*ROUTE:START*/` and `/*ROUTE:END*/`; the page runs A* in the browser (no server route) and gets the alternatives by penalising the cells around each route found. Rebuild with `python3 .claude/skills/dm-citymap/src/build_routing.py`, then `python3 .claude/skills/dm-battlemap/build_combined.py`.

Limits: the poster is an illustration, so narrow alleys are guesses and routes through the densest blocks are approximate; points must be on the city map itself (not the ward lists); no stairs, gates or time of day.

## Travel times for the DM assistant

The same routing is available outside the page: `python .claude/tools/table-chat/table_chat.py map-route "<from>" "<to>"` (MCP `map_route`) and `map-routes` (`map_routes`) for every saved route. `src/route.py` is the Python twin of the page's A* (standard library only, same `routing.png`, costs and 3 mph walking time; results agree with the page to within a few percent). A place is a pin label (the DM's and the players'), a building from `legend.json` (name or code such as C48) or `x,y` in poster pixels; an ambiguous name is refused with the candidates. A call takes about 1.5 seconds. If you change the costs or the alternative-route rules in `citymap.html`, change `route.py` the same way.
