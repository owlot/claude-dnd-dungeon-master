#!/usr/bin/env python3
"""Command line for the table chat server, so the DM assistant (Claude) can run a conversation the same way the DM page does.

Every command prints plain text and exits; `watch` stays running and prints one line per event (run it with the Monitor tool).
The server does the work (drafts, voice, log, memory); this only calls its HTTP API with the DM key from `.dm-token`.

  table_chat.py status
  table_chat.py npcs
  table_chat.py prepare <npc>                       where / scene / who else is there / how each NPC refers to people
  table_chat.py start <npc> [--others a,b] [--location TEXT] [--scene TEXT]    (defaults come from prepare)
  table_chat.py say <speaker-slug|party> "text"     a line from the party (the tablet does this for spoken lines)
  table_chat.py approve ["final text"]              speak and log the waiting draft (or the given text)
  table_chat.py redraft [--to slug] [--party "fixed line"] [--direction "..."]
  table_chat.py tell <npc-slug|room> "fact" --because "why they would know" [--remember]   give an NPC (or everyone present) a fact; the basis is required and logged
  table_chat.py give <npc-slug|room> <object-slug|name> [--look "..."]   an object changes hands: tell only what can be SEEN of it (from its ledger entry)
  table_chat.py amend "wrong text" "right text"      correct a detail in what was already said (log, chat, NPC memory of it)
  table_chat.py withdraw                            take back the waiting line without logging it
  table_chat.py skip                                no reply (logged) / throw a narration draft away
  table_chat.py address <npc-slug>                  who the party is talking to now
  table_chat.py chime <npc-slug> ["what they do or say"]   that NPC speaks up with no new party line
  table_chat.py narrate ["direction"]               the narrator describes something between the lines
  table_chat.py room add|remove <npc-slug>
  table_chat.py answer "fact"  |  answer --unknown  answer an NPC's NEED
  table_chat.py labels <viewer-slug> <key-slug> "how the viewer refers to them"
  table_chat.py restart | stop
  table_chat.py end                                 draft the closing records and save them (log + every NPC's memory)
  table_chat.py end --review                        print the drafts instead of saving
  table_chat.py end --confirm records.json          save edited records ({"npc-slug": {...}})
  table_chat.py discard [--delete-log]              end without saving
  table_chat.py watch                               stream events (one line each)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = os.environ.get("TABLE_CHAT_URL") or f"http://127.0.0.1:{os.environ.get('TABLE_CHAT_PORT', '8020')}"
try:
    KEY = (HERE / ".dm-token").read_text().strip()
except OSError:
    sys.exit("no .dm-token yet: start the server once (run.sh) so it creates one")


def call(path, body=None, method=None, timeout=330):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), method=method or ("GET" if body is None else "POST"),
                                 headers={"x-dm-key": KEY, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail", exc.reason)
        except Exception:
            detail = exc.reason
        sys.exit(f"error: {detail}")
    except (urllib.error.URLError, ConnectionError) as exc:
        sys.exit(f"error: cannot reach the table chat server at {BASE} ({exc}). Is run.sh running?")


def flag(args, name, default=None):
    if name in args:
        i = args.index(name)
        v = args[i + 1] if i + 1 < len(args) else default
        del args[i:i + 2]
        return v
    return default


def switch(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


def show_pending(p):
    if not p:
        return "no line is waiting"
    if p.get("need"):
        return f"NEED from {p['to_name']}: {p['need']}\n  answer with: answer \"fact\"  or  answer --unknown"
    kind = {"line": f"{p.get('speaker_name') or 'The party'} said to {p['to_name']}: {p['party']}", "chime": f"{p['to_name']} speaks up (no new party line)",
            "narration": f"narration, direction: {p.get('direction') or '(none)'}"}[p["kind"]]
    if p.get("error"):
        return f"{kind}\n  the model failed: {p['error']}"
    return f"{kind}\n  DRAFT ({p['to_name']}): {p['draft'] if p['draft'] is not None else '(still drafting)'}"


def show_status(s):
    if not s.get("active"):
        return "no active conversation"
    room = ", ".join(f"{r['display']}{' (addressed)' if r['slug'] == s.get('addressed') else ''}" for r in s.get("room", []))
    return f"active: {room or 'nobody in the room'}\nlog: {s.get('log')}\nlines: {len(s.get('lines', []))}\n{show_pending(s.get('pending'))}"


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, a = argv[0], argv[1:]
    if cmd == "status":
        s = call("/api/health")
        print(f"server ok (llm {s['llm']}, stt {s['stt']}, tts {s['tts']}, session {s['session']}, api {s['api']})")
        st = next_state()
        print(show_status(st))
    elif cmd == "npcs":
        for n in call("/api/npcs"):
            print(f"{n['slug']}: {n['name']} — {n['role'] or '(no role)'} [{n['disposition']}, voice {n['voice']}]")
    elif cmd == "prepare":
        p = call(f"/api/prepare?npc={a[0]}")
        sg = call("/api/labels/suggest", {"slug": a[0], "others": p.get("present", []), "scene": p.get("scene", "")})
        print(json.dumps({**p, "labels": sg["labels"]}, indent=1))
    elif cmd == "start":
        slug = a.pop(0)
        others, loc, scene = flag(a, "--others"), flag(a, "--location"), flag(a, "--scene")
        prep = call(f"/api/prepare?npc={slug}")
        room = others.split(",") if others else prep.get("present", [])
        scene = scene if scene is not None else prep.get("scene", "")
        sg = call("/api/labels/suggest", {"slug": slug, "others": room, "scene": scene})
        r = call("/api/start", {"slug": slug, "others": room, "scene": scene, "location": loc if loc is not None else prep.get("location", ""), "labels": sg["labels"]})
        print("started:", ", ".join(x["name"] for x in r["room"]), "\nlog:", r["log"], "\nscene:", r["scene"])
    elif cmd == "say":
        p = call("/api/say", {"speaker": a[0], "text": " ".join(a[1:])})
        print(show_pending(p))
    elif cmd == "approve":
        text = " ".join(a).strip()
        if not text:
            st = next_state()
            p = st.get("pending")
            if not p or p.get("draft") in (None, ""):
                sys.exit("error: there is no finished draft to approve")
            text = p["draft"]
        r = call("/api/approve", {"text": text})
        print(f"approved and spoken (exchange {r['exchange']})" + (f"; warning: {r['warning']}" if r.get("warning") else ""))
    elif cmd == "redraft":
        body = {}
        for name, key in (("--to", "to"), ("--party", "party"), ("--direction", "direction")):
            v = flag(a, name)
            if v is not None:
                body[key] = v
        print(show_pending(call("/api/regenerate", body)))
    elif cmd == "skip":
        call("/api/skip", {})
        print("done")
    elif cmd == "withdraw":
        call("/api/withdraw", {})
        print("withdrawn: removed from the tablet, nothing logged")
    elif cmd == "tell":
        remember = switch(a, "--remember")
        basis = flag(a, "--because", "")
        r = call("/api/tell", {"to": a[0], "fact": " ".join(a[1:]), "remember": remember, "basis": basis})
        print("told:", ", ".join(r["told"]))
    elif cmd == "give":
        look = flag(a, "--look")
        r = call("/api/give", {"to": a[0], "object": " ".join(a[1:]), "look": look or ""})
        print(f"{r['object']}: told {', '.join(r['told'])}, who can now see: {r['look']}\n(only the look is passed on; add anything else that is visible with --look)")
    elif cmd == "amend":
        r = call("/api/amend", {"find": a[0], "replace": a[1]})
        print(f"corrected in {r['changed']} places (log, chat, saved text, what the NPCs heard)")
    elif cmd == "address":
        call("/api/address", {"to": a[0]})
        print("the party now talks to", a[0])
    elif cmd == "chime":
        print(show_pending(call("/api/chime", {"to": a[0], "direction": " ".join(a[1:])})))
    elif cmd == "narrate":
        print(show_pending(call("/api/narrate", {"direction": " ".join(a)})))
    elif cmd == "room":
        r = call("/api/room", {("add" if a[0] == "add" else "remove"): a[1]})
        print("in the room:", ", ".join(x["name"] for x in r["room"]) or "nobody")
    elif cmd == "answer":
        print(show_pending(call("/api/answer", {"unknown": True} if switch(a, "--unknown") else {"text": " ".join(a)})))
    elif cmd == "labels":
        call("/api/labels", {"labels": {a[0]: {a[1]: " ".join(a[2:])}}})
        print("updated")
    elif cmd == "restart":
        call("/api/restart", {})
        print("restarted: same room and log, nothing said yet")
    elif cmd == "stop":
        call("/api/stop", {})
        print("tablet audio stopped")
    elif cmd == "end":
        if "--confirm" in a:
            recs = json.loads(Path(flag(a, "--confirm")).read_text())
            r = call("/api/end/confirm", {"records": recs})
            print_saved(r)
        elif switch(a, "--review"):
            print(json.dumps(call("/api/end", {}), indent=1))
        else:
            r = call("/api/end/auto", {})
            if r.get("saved"):
                print_saved(r["saved"])
            else:
                print("NOT SAVED:", r["reason"], "\nreview the drafts, fix what is wrong, then save with: end --confirm records.json")
                print(json.dumps(r["drafts"], indent=1))
    elif cmd == "discard":
        r = call("/api/end/discard", {"delete_log": switch(a, "--delete-log")})
        print("ended without saving;", "log deleted" if r["deleted"] else f"{r['exchanges']} exchanges stay in {r['log']}")
    elif cmd == "watch":
        watch()
    else:
        sys.exit(f"unknown command: {cmd}\n\n{__doc__}")


def print_saved(r):
    print(f"saved: {r['exchanges']} exchanges\nlog: {r['log']}\nmemory: {', '.join(r['memories'])}")


def next_state():
    """The current state, read from the first event of the event stream."""
    req = urllib.request.Request(BASE + "/events?role=dm&k=" + KEY)
    with urllib.request.urlopen(req, timeout=15) as r:
        event = None
        for raw in r:
            line = raw.decode().rstrip("\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:") and event == "state":
                return json.loads(line[5:])


def watch():
    """One line per thing the DM assistant must react to. Reconnects when the server restarts (hot reload)."""
    seen = set()
    while True:
        try:
            req = urllib.request.Request(BASE + "/events?role=dm&k=" + KEY)
            with urllib.request.urlopen(req, timeout=60) as r:
                event = None
                for raw in r:
                    line = raw.decode().rstrip("\n")
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        d = json.loads(line[5:])
                        for out in render_event(event, d, seen):
                            print(out, flush=True)
        except Exception:
            pass
        time.sleep(2)


def render_event(event, d, seen):
    if event == "state":
        if not d.get("active"):
            if "idle" in seen:
                return []
            seen.add("idle")
            return ["CONVERSATION: none active"]
        if "room" not in d:  # the version of the event the tablet gets: no room list
            return []
        seen.discard("idle")
        sig = ("room", d["log"], tuple(r["slug"] for r in d["room"]), d.get("addressed"))
        out = []
        if sig not in seen:
            seen.add(sig)
            out.append(f"CONVERSATION: active, in the room: {', '.join(r['display'] for r in d['room']) or 'nobody'}; the party is talking to {next((r['display'] for r in d['room'] if r['slug'] == d.get('addressed')), 'nobody')}")
        if d.get("pending"):
            out += render_event("pending", d["pending"], seen)
        return out
    if event == "line" and d.get("who") == "party":
        return [f"PARTY LINE: {d['name']}: {d['text']}"]
    if event == "pending" and d:
        if d.get("need"):
            key = (d["id"], "need", d["need"])
            return [f"NEED: {d['to_name']} needs a fact: {d['need']}"] if key not in seen and not seen.add(key) else []
        if d.get("error"):
            key = (d["id"], "error")
            return [f"DRAFT FAILED: {d['error']}"] if key not in seen and not seen.add(key) else []
        if d.get("draft"):
            key = (d["id"], "draft", d["draft"])
            if key in seen:
                return []
            seen.add(key)
            what = {"line": f"to {d['speaker_name'] or 'the party'}'s line", "chime": "(speaking up)", "narration": "narration"}[d["kind"]]
            return [f"DRAFT READY: {d['to_name']} {what}: {d['draft']}"]
        return []
    if event == "reply":
        return [f"SPOKEN: {d['name']}: {d['text']}"]
    return []


if __name__ == "__main__":
    main(sys.argv[1:])
