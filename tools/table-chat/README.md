# Table chat

Players speak to an NPC from a tablet on the table; the DM approves every reply before it is spoken. The same server also serves the
table maps (battle map and city map, see *Table maps* below) next to the chat. It keeps the campaign's own records: each approved exchange goes into the NPC log
and the NPC's memory file is updated when the conversation ends.

```
tablet (microphone, speaker) ──voice──▶ laptop server ──▶ Whisper (STT)
                                              │
                                              ├──▶ LLM (NPC file + memory + scene)  ──draft──▶ DM page ──approve/edit──┐
                                              └──▶ TTS (the NPC's locked voice) ◀────────────────────────────────────┘
tablet ◀──────── text + audio of the approved reply ──────────────────────────────┘
```

## Run it

The server has its own virtual environment in this folder (`.venv`, packages in `requirements.txt`). First time, or after cloning:

```bash
cd .claude/tools/table-chat && uv venv .venv --python 3.14 && uv pip install --python .venv/bin/python -r requirements.txt
```

The local LLM (`run-local-llm.sh`) and the speech services (Whisper and the voices, on this laptop or on another machine with a GPU) are separate processes. On the laptop (the DM's machine):

```bash
.claude/tools/table-chat/run.sh
```

**Hot reload is on by default.** When a Python file the server uses changes (`server.py`, `.claude/scripts`, the voice backends),
the server restarts itself within a few seconds and picks the live conversation up again from `.state-<port>.json` (the pending draft
is kept, a draft that was interrupted is asked for again, and the last replies' audio stays in `.audio-<port>/`). Both pages reconnect on
their own and keep what is on screen, so new features appear without stopping anything, even mid-conversation. The pages
themselves are read from disk on each request, so a changed page only needs a reload in the browser. If you turn hot reload off
(`run.sh --no-reload` or `TABLE_CHAT_RELOAD=0`), stop with Ctrl-C and run it again after updates; the DM page warns when the
server it talks to is older than the page.

It prints the links. The **DM link** has a key (`?k=…`, kept in `.dm-token`): open it on the laptop. The **tablet link** has its own key (`?t=…`, kept
in `.table-token`): every tablet route needs it, so the link only works for whoever was given it. The page keeps the key for the tab.

### Tablet over the web (https://<your-site>/<campaign>/chat/)

A web host you control serves your site (`https://<your-site>`). Its Apache proxies `/<campaign>/chat/` to a reverse SSH tunnel from this laptop
(rules in `website/.htaccess`, an offline page in `website/chat-offline.html`). Only the tablet's routes are passed on (the chat, its audio, the map page with its documents and images); the DM page and the DM-only map documents never are.
The host's real HTTPS certificate satisfies the microphone requirement.

```bash
.claude/tools/table-chat/run.sh          # the server (prints the tablet link, also the public one when settings.yaml has public.base_url)
# the tunnel: one SSH reverse forward from the web host's loopback port 18020 to this laptop's server
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -R 127.0.0.1:18020:127.0.0.1:8020 <web-host>
```

Wrap the `ssh` line in a small `while true` loop with a few seconds' sleep if you want it to reconnect by itself. A helper like that,
`run-tunnel.sh`, is ignored by git here because it names your host and SSH setup; keep your own copy next to `run.sh`.

Open `https://<your-site>/<campaign>/chat/?t=<tablet key>` on the tablet. One campaign at a time: the tunnel carries the one server that is running.
If the laptop or the tunnel is down the page says the chat is offline. Rotate the tablet key by deleting `.table-token` and restarting the server.

### Tablet over Tailscale (HTTPS, required for the microphone)

A tablet browser only allows the microphone on an HTTPS page. With Tailscale installed on laptop and tablet, and
*HTTPS certificates* switched on for your tailnet (admin console, DNS page):

```bash
tailscale serve --bg 8020
tailscale serve status        # shows the https://<laptop>.<tailnet>.ts.net address
```

Open that address on the tablet and tap **Tap to start** once: it unlocks sound and asks for the microphone. The server itself
only listens on 127.0.0.1; Tailscale is the only way in. The DM page is protected by its key, so the tablet cannot open it
without the DM link.

## At the table

The system does the paperwork; the DM decides what the NPC says.

1. **Pick the NPC and press Start.** Where and when, the scene, **who else is in the room** and how each NPC refers to each
   person are **prefilled** (model calls reading `party/state.md` and each NPC's own prompt; a few seconds). The scene has only the place, the time and plain
   surroundings, never a name, an item or a plot fact: anything you want the NPC to know, you add yourself. Edit a field only if
   it is wrong. The log file `session-N-npc-NN-slug.md` is created (N from `party/state.md`; the `party/session-N/` folder
   must exist).
2. **The party picks who is speaking.** Each new conversation starts with nobody chosen: the tablet shows a button per player
   character (from `party/characters`) plus *Everyone*, and the talk button stays off until one is tapped. A player taps their
   character, holds the talk button and speaks; the choice is kept until the next conversation. Whisper turns the recording
   into text. The line is shown, logged (`**Party**: Corrin Greenbottle: …`) and sent to the NPC as that character's.
3. **You approve each reply.** The model drafts the NPC's answer from its NPC file and memory. Edit it if you like and press
   *Approve and speak*: that exact text is logged and spoken on the tablet. *Draft again* asks again (you can first fix a
   mishearing in "The party said"). *No reply* logs the line with no answer. *Stop audio* silences the tablet. You can also type
   a line as any character.
4. **End it in one click.** *End and save* drafts the closing record and the NPC's memory entry from the transcript and writes
   them at once: the Conversation End block into the log and a `### Session N` entry into `party/npc-memory/[slug].md` (creating
   the file if the NPC has none). If nothing was answered or the draft fails, it opens the review form instead. The other ways out:
   - *Review before saving…* shows the drafted record to edit first.
   - *End without saving* closes the conversation and keeps the log of the exchanges so far, with no closing record and no
     memory entry.
   - *Discard and delete the log* does the same and deletes the log file (it asks first).

### Several NPCs in the room

Tick *Also in the room* before Start. The prefill only uses what `party/state.md` says about the selected NPC: it is placed where the state names it, and the NPCs listed with it at that place (the same parenthetical) are ticked. If the state never mentions the NPC (Avi, say), the place and the room stay empty with a note showing where the party last met it; the party's own location is never assumed to be the NPC's. The first NPC is the
main one and gets the log; everyone present hears everything, so each NPC keeps its own view of the conversation. During the
conversation:

- **The party is talking to**: buttons at the top switch who the party addresses. The next spoken line is drafted by that NPC.
  The tablet header shows who it is and who else is here, and each reply is shown and spoken with its speaker's name and voice.
- **Who answers** (on the waiting draft) hands the line to someone else and drafts again.
- **Let them speak up** has an NPC add something with no new line from the party (logged as an exchange with
  `*(no new line; X adds to the conversation)*`).
- **Bring into the room / Leaves**: a newcomer hears only what is said from then on; a leaver stays in the records because
  they heard what came before.
- **Narrator**: type a direction ("Avi comes back with Embric, soot on his apron") or leave it empty for a natural small beat,
  and press *Narrate*. The narrator drafts one to three sentences from the scene, the transcript and your direction; you
  edit and approve it like a reply. It is shown on the tablet in italics, spoken in the narrator's voice
  (`website/audio/introductions/narrator.wav` with its `narrator.txt` transcript), logged as `*[Narration]*: …`, and heard by
  every NPC in the room (they see it as `(Narration: …)`). *No reply* throws a draft away without logging it.
- **Stepping out and back**: *Leaves* works for any NPC, the main one included. An NPC who is out hears nothing; when you bring
  them back with *Bring into the room* they remember what they heard before leaving, and narrate what they missed. While nobody
  is in the room the party's lines are refused until someone returns; the narrator still works.
- The log's exchanges read `**Party**: (to Dagna Holdfast) Caelith Morn: …`. At the end every NPC that was present gets a
  `## Conversation End: <name>` block (the main NPC's keeps the standard heading) and a `### Session N` memory entry drafted
  from what *it* heard, in its own words for people. The review form has one section per NPC.

While you read a draft the server speaks it in the background after 3 s (`prefetch_delay_s`), so approving it unchanged starts
the audio at once; starting to edit the draft cancels that job. Replies start after a steady 0.5 s of silence (`lead_in_s`) so
a Bluetooth speaker has time to wake up. Pressing *Start* also wakes the LLM: a model server that loads its model on demand (a big model on a remote box, say) can take a minute or two
on a cold start, so the first draft may be late (the page says so); after that it is about a second.

Measured with everything warm: Whisper 0.3 s for a 4 s recording, the draft 1 to 4 s, VoxCPM on a remote GPU box about 5 s for 9 s of
speech (0.55 times real time).

### What the NPC knows about the people in play (linked facts, NEED)

Before each draft the server runs `.claude/scripts/npc_links.py --scene` on the scene, the party's line and the recent
exchanges, and gives the NPC what its own group knows about every NPC named there (the `## who knows them` tiers; `[secret]`
never). The NPC is told never to invent a fact about a person, item, place or past event: if it would plausibly know something
the files do not say, it replies `NEED: <question>` instead of speaking. The DM page then shows a yellow box: type the fact
(*Answer and draft*) or press *It does not know* (the NPC plays honest ignorance). Approve stays disabled until you answer.
A typed answer is part of what that NPC knows for the rest of the conversation and is saved to its memory file under
`## Linked knowledge` when the conversation ends.

### Who the NPC thinks is speaking

An NPC must not know a name nobody has told it. So the NPC is never given the real name by default: the DM page has, per NPC,
a row for each party member and each other NPC with *how this NPC refers to them*. It is prefilled from the NPC's own files
only: the full name when its prompt (NPC file without the DM-side sections, plus its memory) or your scene text already names
the person, otherwise a description. A model pass writes the description from what the NPC's memory says it saw ("the
green-eyed half-elf who keeps the Stone"), never containing the name; without anything in memory it is the plain
"the halfling rogue" / "the dwarf woman". Edit a
row before *Start*, or change it mid-conversation (*Update labels*) when someone introduces themselves. The tablet and the log
always use the real names; the NPC, and the closing summary drafted from the NPC's point of view, use the labels.

## Claude as the conductor

`table_chat.py` is a command line for everything the DM page does (`python .claude/tools/table-chat/table_chat.py help`), and
`/dm-table-chat` is the skill that has Claude use it: Claude starts the conversation from the prefill (the DM confirms), relays
each party line with its drafted reply for the DM's approval, narrates, switches who is addressed, brings NPCs in and out,
answers NEED, and ends it. `table_chat.py watch` (run by Claude with the Monitor tool) prints one line per event. The server
still writes the NPC log and every NPC's memory entry, so the records are identical whether the DM uses the page or Claude
does; use one or the other for a given conversation, and never together with the `conversation-npc` agents.

## Replay and saved conversations

- **Replay:** every spoken line has a *▶ Replay* button under its chat box. Party lines have *▶ Play in <name>'s voice*: the
  voice is made from the character's intro clip the first time (about 2 s), then kept. Characters' clips need no transcript file:
  the server transcribes each once and keeps the text in `.transcripts/`. *Everyone* has no voice.
- **Replay all:** a button in the tablet's header and under the DM page's transcript plays the conversation from the start, party
  lines in their characters' voices, replies and narration as spoken. It makes any missing character voice on the way.
- **Saved in full:** each recording is also kept for good in `party/session-N/session-N-npc-NN-slug.audio/` (numbered `.wav` files
  plus `lines.json` with every line's text). When a conversation ends (saved or ended without saving), the server voices the party
  lines that have none yet in the background, so the whole conversation can be played later. *Discard and delete the log* removes
  the folder too; *Restart* clears it. The DM page's **Saved conversations** box lists every kept conversation and plays it
  through. The recordings are 0.2 to 1.7 MB each, so a long conversation is tens of MB.

## Table maps (battle map and city map)

The server serves the **Table Maps** page at `/map/`: two tabs, *Battle map* (Combat Positions: grid, walls, fog, tokens, the active
character) and *City map* (the Waterdeep poster with pins, fog, routes). No Claude artifact is involved any more.

- **Links.** `python .claude/tools/table-chat/table_chat.py map-links` prints them. The DM link (`/map/?k=<DM key>`) is the editing view.
  The tablet link (`/map/?t=<tablet key>`, over the web `https://<your-site>/<campaign>/chat/map/?t=…`) is the players' view: the
  tablet moves the active character on the battle map and adds pins and routes on the city map, and can never read the DM-only documents.
  The tablet's chat page also has a **Map** button that opens the map next to the chat (the chat switches to a compact layout).
- **Data.** `campaigns/<campaign>/party/maps/db.json` holds the documents (`dm/state`, `table/state` = the players' filtered copy, `dm/overlay`,
  `moves/table`, `table/reply`, `city/state`, `citypub/state`, `citypins/<id>`); `assets.json` lists the images by repo-relative path (the
  poster in `sources/`, portraits from `website/<campaign>/assets/world-images/`; register one with `map-asset <file>`). Nothing is copied.
  `db.json` is the only copy of the live board, pins and routes: commit it now and then.
- **City map pins.** A new pin offers a dropdown of the places the party knows (the website's `world.json` Places cards with the text from
  `world-public.json`), fills the label and description from them, and shows the location's picture when one exists. The DM also sees
  locations the players do not know yet, marked so, and they start hidden. Tapping a pin opens its card (description, picture, saved routes).
- **Routes.** *Measure* measures a path and can save it; *Find routes* takes two spots and shows up to three walking routes along the poster's
  streets (the shortest highlighted) that can be saved too. A saved route is listed on the card of the pin it starts or ends at. The routing
  grid is read off the poster by `.claude/skills/dm-citymap/src/build_routing.py`.
- **Claude's side.** `table_chat.py map-docs | map-get | map-col | map-set | map-merge | map-delete | map-asset | map-assets | map-links`
  and the MCP `map_*` tools read and write the documents (never hand-write `table/state`: the DM page rebuilds it). For travel times,
  `map-route "<from>" "<to>"` (MCP `map_route`) gives the saved routes between two places and up to three computed ones with distance and
  walking time at 3 mph; `map-routes` lists every saved route. A place is a pin label, a building from the poster's legend (name or code
  like C48) or `x,y`.
- **Skills.** `/dm-battlemap` (load an encounter's maps, sync, move) and `/dm-citymap` (the city map and its data); both are in `.claude/skills/`.

## MCP server

`mcp_server.py` (standard library only) exposes the same commands as 33 typed MCP tools: 22 for the conversation (`table_chat_status`,
`_npcs`, `_prepare`, `_start`, `_say`, `_approve`, `_redraft`, `_skip`, `_withdraw`, `_amend`, `_tell`, `_give`, `_address`, `_chime`,
`_narrate`, `_room`, `_answer`, `_labels`, `_restart`, `_stop_audio`, `_end`, `_discard`) and 11 for the maps (`map_docs`, `map_get`,
`map_collection`, `map_set`, `map_merge`, `map_delete`, `map_asset`, `map_assets`, `map_links`, `map_route`, `map_routes`). It is a thin
layer over `table_chat.py`, so the behaviour is identical. It is
registered in the project's `.mcp.json`; Claude Code asks once to approve it. Events still come through
`table_chat.py watch`.

## Configuration

Settings live in `settings.yaml` next to the server. It is yours and ignored by git; `settings.example.yaml` is the template (`run.sh` copies it the first time, with a note to edit the addresses). The sections: the `llm` section (address, model, `extra_body`; the local llama-server
started by `run-local-llm.sh`, with a remote server's address kept as a comment), `stt` (a Whisper server) and `tts` (`kind: tts-serve`
or `breeze`, the address of the machine that runs it). The LLM key, when the endpoint needs one, comes from `TABLE_CHAT_LLM_KEY` or a file `llm_api_key`
in this folder. An optional `config.json` in this folder (see `config.example.json`), or the file `TABLE_CHAT_CONFIG` points at,
overrides anything in `settings.yaml`. Restart the server after editing `settings.yaml` (touching `server.py` makes the hot reload do it).
Voices are the locked clips in `website/<campaign>/audio/introductions/` (with the saved `.txt` transcript) or the generic
stand-in from `party/voice-overrides.json`; an NPC with no voice gets text only.

## What it does not do

- It never speaks without the DM's approval, and the NPC knows only its NPC file, its memory file and the scene text you
  give it (`.claude/rules/npc-memory.md`). It does not know what the party did elsewhere.
- Rolls, checks and consequences stay with the DM, as everywhere else.
- Tested with a real remote LLM server, a real Whisper server (WAV, WebM/Opus and MP4/AAC recordings all transcribed perfectly), real
  VoxCPM and Breeze voices, and both pages driven in a browser pane. **Not tested:** the real microphone on a tablet (the
  pane blocks it), and the Tailscale HTTPS link. Try both once before a session.
