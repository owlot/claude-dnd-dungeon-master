#!/usr/bin/env python3
"""MCP server (stdio, standard library only) that exposes the table chat to Claude as typed tools.

It is a thin layer over table_chat.py, which talks to the table chat server's HTTP API: every tool builds the same arguments the command
line takes and returns the same text. Nothing here knows how a conversation works. Events (a party line, a finished draft) are still
read with `table_chat.py watch` through the Monitor tool; MCP tools cannot push them.

Register it for the project in `.mcp.json` (done) and approve it when Claude Code asks. Environment: TABLE_CHAT_PORT / TABLE_CHAT_URL.
"""
import contextlib
import io
import json
import sys

import table_chat as tc



def schema(props, required=()):
    return {"type": "object", "properties": {k: ({"type": "boolean", "description": d[1:]} if d.startswith("?") else {"type": "string", "description": d}) for k, d in props.items()},
            "required": list(required), "additionalProperties": False}


def one_of(a):
    """The document argument of map-set / map-merge: inline JSON, or @file."""
    if a.get("file") and a.get("json"):
        sys.exit("give either json or file, not both")
    if a.get("file"):
        return "@" + a["file"]
    if a.get("json"):
        return a["json"]
    sys.exit("give json or file")


# name -> (description, input schema, argv builder)
TOOLS = {
    "table_chat_status": ("Server health and the live conversation: who is in the room, who is addressed, any waiting draft or NEED.", schema({}), lambda a: ["status"]),
    "table_chat_npcs": ("List the NPCs that can be talked to (slug, name, role, disposition, voice).", schema({}), lambda a: ["npcs"]),
    "table_chat_prepare": ("Prefill for a conversation with an NPC from party/state.md and the NPC's own files: place, scene, who else is there, and how each NPC refers to each person. Show it to the DM before starting.",
                           schema({"npc": "NPC slug"}, ["npc"]), lambda a: ["prepare", a["npc"]]),
    "table_chat_start": ("Start a conversation. Run /dm-checkpoint-log first and let the DM confirm the prefill. Omitted fields use the prefill.",
                         schema({"npc": "main NPC slug", "others": "comma-separated slugs of the other NPCs in the room", "location": "where and when (log header)", "scene": "what the NPC can perceive, plus DM-approved facts"}, ["npc"]),
                         lambda a: ["start", a["npc"]] + (["--others", a["others"]] if a.get("others") else []) + (["--location", a["location"]] if "location" in a else []) + (["--scene", a["scene"]] if "scene" in a else [])),
    "table_chat_say": ("A line from the party typed by the DM (spoken lines arrive from the tablet by themselves). Drafts the addressed NPC's reply.",
                       schema({"speaker": "player-character slug, or 'party' for everyone", "text": "what was said"}, ["speaker", "text"]), lambda a: ["say", a["speaker"], a["text"]]),
    "table_chat_approve": ("Speak and log the waiting draft, or the exact text given. Only after the DM has approved it.",
                           schema({"text": "the DM's final wording; omit to approve the draft as it is"}), lambda a: ["approve"] + ([a["text"]] if a.get("text") else [])),
    "table_chat_redraft": ("Draft the waiting reply again. 'to' hands the line to another NPC, 'party' corrects a mistranscribed line, 'direction' steers a narration or speak-up.",
                           schema({"to": "NPC slug", "party": "corrected party line", "direction": "cue for the narrator or a speaking-up NPC"}),
                           lambda a: ["redraft"] + sum([[f"--{k}", a[k]] for k in ("to", "party", "direction") if a.get(k)], [])),
    "table_chat_skip": ("No reply: log the line with no answer, or throw a narration draft away.", schema({}), lambda a: ["skip"]),
    "table_chat_withdraw": ("Take back the waiting line (sent by mistake or with the wrong tool): it vanishes from the tablet and nothing is logged.", schema({}), lambda a: ["withdraw"]),
    "table_chat_amend": ("Correct a wrong detail in something already said (log, tablet chat, saved text and what the NPCs heard). Use for facts the files contradict, not for rewording.",
                         schema({"find": "the wrong text, exactly as it appears", "replace": "the correct text"}, ["find", "replace"]), lambda a: ["amend", a["find"], a["replace"]]),
    "table_chat_tell": ("Give an NPC, or everyone present ('room'), a fact before it has to ask: what an item is made of, what the NPC knows. The narrator can use room facts. Only for facts we have established that the NPC would know (it can perceive them, its files say so, or the DM ruled it); the basis is required and logged. Never use it to invent or to hand over what the NPC could not know.",
                        schema({"to": "NPC slug, or 'room' for everyone present", "fact": "the fact, written as what the NPC sees or knows", "basis": "why the NPC would know it: it can see it, its files say so, or the DM ruled it", "remember": "?true to also save it to the NPC's memory"}, ["to", "fact", "basis"]),
                        lambda a: ["tell", a["to"], a["fact"], "--because", a["basis"]] + (["--remember"] if a.get("remember") else [])),
    "table_chat_give": ("An object changes hands: the NPC (or everyone present, 'room') is told only what can be SEEN of it, taken from the object's ledger entry (party/objects). History, origin, value and magic are left out. If the ledger has no look, supply 'look' yourself.",
                        schema({"to": "NPC slug, or 'room'", "object": "object slug or name", "look": "the visible look, if the ledger has none or the DM described it"}, ["to", "object"]),
                        lambda a: ["give", a["to"], a["object"]] + (["--look", a["look"]] if a.get("look") else [])),
    "table_chat_address": ("Switch who the party is talking to.", schema({"npc": "NPC slug"}, ["npc"]), lambda a: ["address", a["npc"]]),
    "table_chat_chime": ("Have an NPC speak up with no new party line; 'direction' says what they do or say.",
                         schema({"npc": "NPC slug", "direction": "what they do or say"}, ["npc"]), lambda a: ["chime", a["npc"]] + ([a["direction"]] if a.get("direction") else [])),
    "table_chat_narrate": ("The narrator describes something between the lines; heard by every NPC in the room. Empty direction gives a natural small beat.",
                           schema({"direction": "what the narrator should describe"}), lambda a: ["narrate"] + ([a["direction"]] if a.get("direction") else [])),
    "table_chat_room": ("Bring an NPC into the room or let one leave. A returning NPC remembers what it heard before leaving.",
                        schema({"action": "add or remove", "npc": "NPC slug"}, ["action", "npc"]), lambda a: ["room", a["action"], a["npc"]]),
    "table_chat_answer": ("Answer an NPC's NEED with a fact, or say it does not know.",
                          schema({"fact": "the fact the NPC knows", "unknown": "?true if the NPC would not know it"}), lambda a: ["answer", "--unknown"] if a.get("unknown") else ["answer", a.get("fact", "")]),
    "table_chat_labels": ("Change how one NPC refers to a person (for example after an introduction).",
                          schema({"viewer": "NPC slug that uses the label", "key": "slug of the person (PC or NPC)", "label": "how the viewer refers to them"}, ["viewer", "key", "label"]),
                          lambda a: ["labels", a["viewer"], a["key"], a["label"]]),
    "table_chat_restart": ("Start the same conversation over: same room and log, nothing said yet, nothing saved.", schema({}), lambda a: ["restart"]),
    "table_chat_stop_audio": ("Silence the tablet.", schema({}), lambda a: ["stop"]),
    "table_chat_end": ("End the conversation and save it: drafts each NPC's closing record from what it heard and writes the log blocks and memory entries. 'review' prints the drafts instead.",
                       schema({"review": "?true to print the drafts without saving"}), lambda a: ["end", "--review"] if a.get("review") else ["end"]),
    "map_docs": ("The battle map and the city map (served by the table chat at /map/): list the stored documents.", schema({}), lambda a: ["map-docs"]),
    "map_get": ("Read a map document as JSON. dm/state = the DM's battle map, table/state = what the players see, moves/table = pending player moves, city / citypub / citypins/<id> = the city map.",
                schema({"path": "document path", "out": "optional: write the document to this file (a path inside the repo) instead of returning it, for large documents"}, ["path"]),
                lambda a: ["map-get", a["path"]] + (["--out", a["out"]] if a.get("out") else [])),
    "map_collection": ("Read every document of a map collection (for example citypins).", schema({"name": "collection name"}, ["name"]), lambda a: ["map-col", a["name"]]),
    "map_set": ("Replace a map document with the given JSON. Read it first with map_get and change only what the DM asked for.",
                schema({"path": "document path", "json": "the full new document, as JSON text", "file": "alternatively, a JSON file (a path inside the repo) holding the full document"}, ["path"]),
                lambda a: ["map-set", a["path"], one_of(a)]),
    "map_merge": ("Merge top-level keys into a map document (creates it if missing); the other keys stay as they are.",
                  schema({"path": "document path", "json": "JSON object with the keys to set", "file": "alternatively, a JSON file holding the keys to set"}, ["path"]),
                  lambda a: ["map-merge", a["path"], one_of(a)]),
    "map_delete": ("Delete a map document.", schema({"path": "document path"}, ["path"]), lambda a: ["map-delete", a["path"]]),
    "map_asset": ("Register a map image from a file on the DM's machine (for example campaigns/<c>/sources/...) and get the asset id the map documents refer to.",
                  schema({"file": "path of the image file"}, ["file"]), lambda a: ["map-asset", a["file"]]),
    "map_assets": ("List the registered map images.", schema({}), lambda a: ["map-assets"]),
    "map_route": ("How far and how long on foot between two places on the Waterdeep city map: saved routes between them (DM's and players') plus up to three computed street routes, the shortest first (walking at 3 mph, about 264 ft a minute). Use it when the party asks how long it takes to get somewhere. Each place is a pin label, a building from the poster's printed legend (name or code such as C48) or 'x,y' in poster pixels. The poster is an illustration: narrow alleys are approximate, so say 'about'.",
                  schema({"origin": "where from: pin label, legend building or code, or x,y", "destination": "where to"}, ["origin", "destination"]), lambda a: ["map-route", a["origin"], a["destination"]]),
    "map_routes": ("List every saved route on the city map (the DM's and the players') with distance and walking time.", schema({}), lambda a: ["map-routes"]),
    "map_links": ("The map page links for the DM and for the tablet.", schema({}), lambda a: ["map-links"]),
    "table_chat_discard": ("End without saving anything to memory; optionally delete the log.", schema({"delete_log": "?true to delete the log file"}), lambda a: ["discard"] + (["--delete-log"] if a.get("delete_log") else [])),
}


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            tc.main(argv)
        except SystemExit as exc:
            code = 1 if exc.code not in (None, 0) else 0
            if isinstance(exc.code, str):
                print(exc.code)
        except Exception as exc:  # a failing tool must not take the server down
            code = 1
            print(f"error: {exc}")
    return (out.getvalue() + err.getvalue()).strip() or "done", code != 0


def reply(msg_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": msg_id}
    msg["error" if error else "result"] = error or result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(m):
    method, mid = m.get("method"), m.get("id")
    if method == "initialize":
        reply(mid, {"protocolVersion": m.get("params", {}).get("protocolVersion", "2025-03-26"), "capabilities": {"tools": {}},
                    "serverInfo": {"name": "table-chat", "version": "1.0"}})
    elif method == "tools/list":
        reply(mid, {"tools": [{"name": n, "description": d, "inputSchema": sch} for n, (d, sch, _) in TOOLS.items()]})
    elif method == "tools/call":
        p = m.get("params", {})
        tool = TOOLS.get(p.get("name"))
        if not tool:
            reply(mid, error={"code": -32602, "message": f"unknown tool {p.get('name')}"})
            return
        text, is_error = run(tool[2](p.get("arguments") or {}))
        reply(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})
    elif method == "ping":
        reply(mid, {})
    elif mid is not None:
        reply(mid, error={"code": -32601, "message": f"method not found: {method}"})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    main()
