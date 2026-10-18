#!/usr/bin/env python3
"""Table chat: talk to NPCs by voice from a tablet on the table, with the DM approving every reply.

Tablet (/)   hold the button and speak; sees the conversation; hears the NPC's reply.
DM (/dm?k=)  picks the NPC and scene, sees what the party said, edits or approves the drafted reply, ends the conversation.
Pipeline     speech -> Whisper (STT) -> NPC brain (LLM, from the NPC file and memory file) -> DM approval -> TTS -> tablet.
Records      every approved exchange is appended to the NPC log (.claude/rules/npc-log-format.md); ending the conversation
             writes the Conversation End block and the memory entry (.claude/rules/npc-memory.md). Nothing is a snapshot.

Run with run.sh. Only the Python standard library plus fastapi, uvicorn, httpx and python-multipart are needed (all in
this folder's .venv). See README.md for Tailscale and configuration.
"""
import array
import asyncio
import io
import json
import math
import os
import re
import secrets
import shutil
import sys
import time
import uuid
import wave
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for sub in (".claude/scripts", ".claude/tools/backends/tts-serve", ".claude/tools/backends/breeze"):
    sys.path.insert(0, str(REPO / sub))
import npc_files as ntw  # noqa: E402  (NPC file sections and the NPC prompt builder, in this folder)
from breeze_client import _multipart as breeze_multipart  # noqa: E402
from ttsserve_client import Client as TTSServeClient  # noqa: E402

# ----------------------------------------------------------------------------------------------- configuration

DEFAULTS = {
    "campaign": "waterdeep-dragon-heist",
    "data_root": str(REPO),  # folder holding campaigns/ and website/
    "llm": {"base_url": None, "model": None, "max_tokens": 300, "temperature": 0.8, "extra_body": {}},
    "stt": {"base_url": "http://localhost:8181", "timeout": 60},
    "tts": {"kind": "tts-serve", "url": "http://localhost:7500", "timeout": 120},  # kind: tts-serve | breeze
    "lead_in_s": 0.5,  # silence before every reply, so a Bluetooth speaker has time to wake up
    "history_turns": 12,
    "prefetch_delay_s": 3.0,  # how long a draft sits before it is spoken in the background (cancelled if the DM edits it)
    "port": int(os.environ.get("TABLE_CHAT_PORT", "8020")),
}


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:  # settings.yaml in this folder is the starting point for the LLM, STT and TTS addresses
        import yaml
        tw = yaml.safe_load((HERE / "settings.yaml").read_text(encoding="utf-8")) or {}
        for key in ("llm",):
            if tw.get(key):
                _merge(cfg[key], {k: v for k, v in tw[key].items() if k in cfg[key]})
        if (tw.get("stt") or {}).get("base_url"):
            cfg["stt"]["base_url"] = tw["stt"]["base_url"]
        if (tw.get("stt") or {}).get("timeout"):
            cfg["stt"]["timeout"] = tw["stt"]["timeout"]
        if (tw.get("public") or {}).get("base_url"):
            cfg["public"] = {"base_url": tw["public"]["base_url"]}
        if (tw.get("tts") or {}).get("base_url"):
            cfg["tts"]["url"] = tw["tts"]["base_url"]
        for k in ("kind", "timeout"):
            if (tw.get("tts") or {}).get(k):
                cfg["tts"][k] = tw["tts"][k]
    except Exception:
        pass
    path = Path(os.environ.get("TABLE_CHAT_CONFIG", HERE / "config.json"))
    if path.exists():
        _merge(cfg, json.loads(path.read_text(encoding="utf-8")))
    return cfg


CFG = load_config()
DATA = Path(CFG["data_root"])
CAMP = CFG["campaign"]
CAMP_DIR = DATA / "campaigns" / CAMP


def llm_key():
    env = os.environ.get("TABLE_CHAT_LLM_KEY", "").strip()
    if env:
        return env
    try:
        raw = (HERE / "llm_api_key").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"^\s*llm_api_key\s*=\s*(\S+)", raw, re.M)
    return (m.group(1) if m else raw.strip()).strip("\"'")


def dm_token():
    path = HERE / ".dm-token"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(18), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


DM_KEY = dm_token()


def table_token():
    path = HERE / ".table-token"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(18), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


TABLE_KEY = table_token()  # the tablet's key: the tablet page is reachable from outside (reverse tunnel), so every tablet route needs it
API_LEVEL = 9  # raise this when a page starts to need a new route; the DM page warns when the running server is older

# ----------------------------------------------------------------------------------------------- state and events

app = FastAPI(title="Table chat")
import map_service  # noqa: E402  (the standalone map: documents, assets and pages for the battle map and the city map)
map_service.init(CAMP_DIR, REPO, DM_KEY, TABLE_KEY, REPO / ".claude" / "skills" / "dm-battlemap" / "combined.html")
app.include_router(map_service.router)
clients = {"table": set(), "dm": set()}
conv = None  # the live conversation
pending = None  # {"id", "party", "draft"} waiting for the DM
STATE_FILE = HERE / f".state-{CFG['port']}.json"  # the live conversation, so a restart (hot reload) does not lose it
AUDIO_DIR = HERE / f".audio-{CFG['port']}"  # the last replies, so their links keep working across a restart
START_TS = int(time.time())
prefetch = None  # {"text", "task"}: the draft is spoken in the background while the DM reads it


def save_state():
    """Write the live conversation and the pending draft to disk (or remove the file when there is no conversation)."""
    try:
        if not conv:
            STATE_FILE.unlink(missing_ok=True)
            return
        data = {"conv": {**{k: v for k, v in conv.items() if k != "log"}, "log": str(conv["log"].relative_to(DATA))}, "pending": pending}
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(STATE_FILE)
    except Exception:
        pass


def load_state():
    """Restore a conversation that was live when the server last stopped. Returns True when one was restored."""
    global conv, pending
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        c = data["conv"]
        if "main" not in c:  # saved by an older server version: cannot be resumed
            return False
        c["log"] = DATA / c["log"]
        if c["log"].exists():
            conv, pending = c, data.get("pending")
            return True
    except Exception:
        pass
    return False


def audio_folder(c):
    """Where a conversation's recordings are kept for good: next to its log (session-N-npc-NN-slug.audio/)."""
    return c["log"].with_suffix(".audio")


def save_lines(c):
    """lines.json beside the recordings: the whole conversation in order, so it can be replayed later."""
    d = audio_folder(c)
    if not d.is_dir():
        return
    rows = [{"who": l["who"], "name": l["name"], "text": l["text"], "file": l.get("file")} for l in c["lines"]]
    (d / "lines.json").write_text(json.dumps({"title": c["npcs"][c["main"]]["name"], "location": c["location"], "session": c["session"], "lines": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


def keep_audio(c, line, wav):
    """Keep a line's recording with the conversation. Returns nothing; the line remembers its file."""
    d = audio_folder(c)
    d.mkdir(exist_ok=True)
    c["aseq"] = c.get("aseq", 0) + 1
    who = re.sub(r"[^a-z0-9]+", "-", (line.get("speaker") or line.get("slug") or line["who"]).lower()).strip("-") or "line"
    name = f"{c['aseq']:03d}-{who}.wav"
    (d / name).write_bytes(wav)
    line["file"] = name
    save_lines(c)


async def finalize_audio(c):
    """After the conversation ends: make the voice of every party line that has none yet, so the saved conversation can be played
    in full. Runs in the background; a failure on one line does not stop the others."""
    for line in list(c["lines"]):
        cached = AUDIO_DIR / f"{(line.get('audio') or '').rsplit('/', 1)[-1]}"
        if line.get("audio") and not line.get("file") and cached.is_file():  # spoken before recordings were kept
            await asyncio.to_thread(keep_audio, c, line, cached.read_bytes())
        if line["who"] == "party" and not line.get("file"):
            slug = line.get("speaker") or "party"
            if slug == "party" or not find_voice(slug)[0]:
                continue
            try:
                wav = await speak(slug, line["text"])
                if wav:
                    await asyncio.to_thread(keep_audio, c, line, wav)
            except Exception:
                pass
    save_lines(c)


def store_audio(aid, data):
    AUDIO_DIR.mkdir(exist_ok=True)
    (AUDIO_DIR / f"{aid}.wav").write_bytes(data)
    for old in sorted(AUDIO_DIR.glob("*.wav"), key=lambda p: p.stat().st_mtime)[:-30]:
        old.unlink(missing_ok=True)


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def publish(roles, event, data):
    save_state()  # every change of state is announced through here, so this is where it is kept
    for role in roles:
        for q in list(clients[role]):
            q.put_nowait(sse(event, data))


def public_state():
    if not conv:
        return {"active": False}
    by_name = {m["name"]: m["slug"] for m in party_members()}
    for l in conv["lines"]:  # lines logged before speakers were recorded: find the character by name
        if l["who"] == "party" and not l.get("speaker"):
            l["speaker"] = by_name.get(l["name"], "party")
    npcs = conv["npcs"]
    a = conv["addressed"]
    return {"active": True, "cid": conv["id"], "npc": npcs[a]["display"] if a else "Nobody is here right now", "slug": a,
            "also": [npcs[x]["display"] for x in conv["order"] if x != a], "lines": conv["lines"], "waiting": bool(pending)}


def dm_state():
    s = public_state()
    s["pending"] = pending
    s["members"] = party_members()
    if conv:
        s["room"] = [{"slug": x, "name": conv["npcs"][x]["name"], "display": conv["npcs"][x]["display"], "labels": conv["npcs"][x]["labels"]} for x in conv["order"]]
        s["main"], s["addressed"] = conv["main"], conv["addressed"]
        s["log"] = str(conv["log"].relative_to(DATA))
        s["scene"] = conv["scene"]
    return s


def check_dm(key):
    if not key or not secrets.compare_digest(key, DM_KEY):
        raise HTTPException(status_code=403, detail="DM key missing or wrong")


def check_table(key, dm_key=""):
    """The tablet key (or, for the DM's own page, the DM key)."""
    if key and secrets.compare_digest(key, TABLE_KEY):
        return
    if dm_key and secrets.compare_digest(dm_key, DM_KEY):
        return
    raise HTTPException(status_code=403, detail="Tablet key missing or wrong: open the tablet link with its ?t= key")


# ----------------------------------------------------------------------------------------------- campaign files


def session_number():
    text = (CAMP_DIR / "party" / "state.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*Session #\*\*:\s*(\d+)", text)
    if not m:
        raise HTTPException(status_code=409, detail="could not read the session number from party/state.md")
    return int(m.group(1))


def party_members():
    """The player characters (party/characters files of type pc): slug, name, and a short description from race and class."""
    out = []
    for path in sorted((CAMP_DIR / "party" / "characters").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        secs = ntw.sections(text)
        char = secs.get("character", "")
        if ntw.field(char, "type") != "pc":
            continue
        def row(label):
            m = re.search(rf"\*\*{label}\*\*\s*\|\s*([^|\n]+?)\s*\|", text)
            return re.sub(r"\s*\([^)]*\)", "", m.group(1)).strip().lower() if m else ""
        race, klass = row("Race"), row("Class")
        out.append({"slug": path.stem, "name": ntw.field(char, "name") or path.stem,
                    "short": f"the {race} {klass}".replace("  ", " ").strip() if (race or klass) else "an adventurer"})
    return out


def npc_brief(slug):
    secs = ntw.sections((CAMP_DIR / "info" / "npcs" / f"{slug}.md").read_text(encoding="utf-8"))
    char = secs.get("character", "")
    return {"slug": slug, "name": ntw.field(char, "name") or slug, "race": ntw.field(char, "race").lower(),
            "gender": ntw.field(char, "gender").lower(), "role": ntw.field(char, "role")}


def generic_desc(slug):
    """A plain description of an NPC for someone who does not know the name: 'the dwarf woman'."""
    b = npc_brief(slug)
    who = {"female": "woman", "male": "man"}.get(b["gender"], "person")
    return f"the {b['race']} {who}" if b["race"] else f"the {who}"


def names_known(prompt, name):
    """True when the text names the person (full name or first name, as whole words)."""
    prompt = prompt.lower()
    words = {name} | ({name.split()[0]} if name.split()[0].lower() not in {"the", "a", "an", "lord", "lady", "sir", "captain"} else set())
    return any(re.search(rf"\b{re.escape(w.lower())}\b", prompt) for w in words)


def label_defaults(viewer, others, scene=""):
    """How the NPC `viewer` refers to each party member and each other NPC in the room: by name when what it knows (its prompt:
    NPC file without the DM-side sections, plus its memory, plus the scene text) already names them, else a description.
    An NPC must not know a name it was never told."""
    prompt = build_system_prompt(viewer, scene)[0]
    out = {"party": "the party"}
    for m in party_members():
        out[m["slug"]] = m["name"] if names_known(prompt, m["name"]) else m["short"]
    for o in others:
        if o != viewer:
            b = npc_brief(o)
            out[o] = b["name"] if names_known(prompt, b["name"]) else generic_desc(o)
    return out


async def refine_labels(viewer, labels, others, scene=""):
    """Replace the generic descriptions with the NPC's own ('the green-eyed half-elf who keeps the Stone') when its memory has
    them. Names are never introduced here: a description may not contain the person's name."""
    names = {m["slug"]: m["name"] for m in party_members()}
    names.update({o: npc_brief(o)["name"] for o in others if o != viewer})
    unknown = {k: labels[k] for k in names if labels.get(k) and labels[k] != names[k]}
    if not unknown:
        return labels
    knowledge = build_system_prompt(viewer, scene)[0]
    listing = "\n".join(f'- "{k}": fallback "{v}"' for k, v in unknown.items())
    prompt = (f"{npc_brief(viewer)['name']} is an NPC in a fantasy roleplaying game. Below is everything it knows, then a list of people in "
              "the room whose names it does NOT know. For each, write how it thinks of them: three to eight words starting with \"the\", using "
              "only what its knowledge says it has seen or been told about that person (look, race, trade, something they did). If its knowledge "
              "says nothing about them, repeat the fallback. Never write the person's name. Reply with a JSON object mapping each key to its description.\n\n"
              f"PEOPLE:\n{listing}\n\nKNOWLEDGE:\n{knowledge[:6000]}")
    try:
        raw = await llm_chat([{"role": "system", "content": "You write short, factual descriptions."}, {"role": "user", "content": prompt}], max_tokens=300, temperature=0.2)
        got = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
    except Exception:
        return labels
    out = dict(labels)
    for k, fallback in unknown.items():
        v = str(got.get(k, "")).strip().strip('"')
        tokens = [t for t in re.split(r"\W+", names[k]) if len(t) >= 3]
        if v and len(v) <= 70 and not any(re.search(rf"\b{re.escape(t)}\b", v, re.I) for t in tokens):
            out[k] = v[:1].lower() + v[1:] if v.lower().startswith("the ") else v
    return out


def speaker_name(key):
    """The name shown on the tablet and in the log for a line from the party."""
    for m in party_members():
        if m["slug"] == key:
            return m["name"]
    return "The party"


def says(label, text):
    return f"{label[:1].upper()}{label[1:]} says: {text}"


def state_excerpt():
    """The where-and-when lines of party/state.md (current location, time of day, in-game date)."""
    text = (CAMP_DIR / "party" / "state.md").read_text(encoding="utf-8")
    keep = []
    for line in text.splitlines():
        m = re.match(r"- \*\*(In-Game Date|Current Location|Time of Day)\*\*:\s*(.*)", line)
        if m:
            keep.append(f"{m.group(1)}: {m.group(2)[:900]}")
    return "\n".join(keep)


def state_mentions(npc_slug):
    """(evidence, others): the where-and-when sentences that name this NPC, and the other NPCs listed with it at that place (the
    same parenthetical, or the same sentence when there is none). Only an explicit mention places an NPC; the party's own
    location says nothing about where an NPC is."""
    me = npc_brief(npc_slug)
    text = state_excerpt()
    evidence = [x for x in re.split(r"(?<=[.;])\s+", text) if x.strip() and names_known(x, me["name"])]
    groups = re.findall(r"\(([^)]*)\)", text)
    units = [g for g in groups if names_known(g, me["name"])] or \
            [re.sub(r"\([^)]*\)", "", x) for x in evidence]
    others = [p.stem for p in npc_files() if p.stem != npc_slug and any(names_known(u, npc_brief(p.stem)["name"]) for u in units)]
    return evidence, others


def last_seen(npc_slug):
    """The heading of the NPC's newest memory entry: where the party last met it (possibly long ago)."""
    mem = CAMP_DIR / "party" / "npc-memory" / f"{npc_slug}.md"
    if not mem.exists():
        return ""
    heads = re.findall(r"^### (Session \d+ — .+)$", mem.read_text(encoding="utf-8"), re.M)
    return heads[-1] if heads else ""


PREP_PROMPT = """You prepare the header for a conversation in which a party of adventurers has come to speak with the NPC {name}.
Write JSON with two keys.
"location": the place where {name} is NOW, taken ONLY from the EVIDENCE below. The party's own location is not evidence: {name} is
not necessarily with the party. If the evidence does not say where {name} is, write "". Never guess.
"scene": one to three short plain sentences about the ordinary physical surroundings {name} can see and hear there (indoors or
outdoors, weather, light, crowd or quiet), only if the evidence describes that place; otherwise nothing about the place. It always ends
with the sentence "The party has come to speak with {name}."
The scene is given to the NPC as everything it can perceive, so it must NOT contain: any person's name other than {name}, any item,
creature, secret, plot fact or rumour, any statement about who else is or is not present, anything about where else the party or anyone
else is or has been, or anything that {name} could not see from where it stands. Reply with the JSON object only.

EVIDENCE (state lines that name {name}):
{evidence}

THE NPC ({name}): {role}"""


def scrub_scene(scene, npc_name):
    """Drop sentences that say who else is or is not present (the model sometimes invents them) and make sure the scene ends
    with the line that the party has come to speak with the NPC."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(scene).split()))
    kept = [x for x in sentences if x and not re.search(r"empty of|no one|nobody|alone|other people|no other|anyone else|unoccupied|deserted", x, re.I)]
    closing = f"The party has come to speak with {npc_name}."
    kept = [x for x in kept if x.rstrip(".") != closing.rstrip(".")] + [closing]
    return " ".join(kept)


@app.get("/api/prepare")
async def api_prepare(npc: str, x_dm_key: str = Header(default="")):
    """Prefill location and scene for this NPC from the campaign state, so the DM only has to press Start."""
    check_dm(x_dm_key)
    path = CAMP_DIR / "info" / "npcs" / f"{npc}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="unknown NPC")
    summ = npc_summary(path)
    mine, present = state_mentions(npc)
    hint = last_seen(npc)
    time_line = next((l for l in state_excerpt().splitlines() if l.startswith("Time of Day")), "")
    time_short = re.sub(r"^Time of Day:\s*", "", time_line).split(".")[0].split(";")[0].strip()
    out = {"location": "", "scene": scrub_scene("", summ["name"]), "present": present[:5], "last_seen": hint, "time": time_short}
    if not mine:  # nothing places this NPC: the DM says where; no model call can improve on that
        out["note"] = f"party/state.md does not say where {summ['name']} is, so the place and the room are left for you to fill in."
        return out
    prompt = PREP_PROMPT.format(name=summ["name"], role=summ["role"] or "(no role recorded)", evidence="\n".join(mine))
    try:
        raw = await llm_chat([{"role": "system", "content": "You write short, factual scene headers."}, {"role": "user", "content": prompt}], max_tokens=350, temperature=0.2)
        j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        scene = j.get("scene", "")
        if isinstance(scene, list):
            scene = "\n".join(str(x) for x in scene)
        loc = str(j.get("location", "")).strip()
        out.update({"location": f"{loc}, {time_short}" if loc and time_short else loc, "scene": scrub_scene(scene, summ["name"])})
        return out
    except Exception as exc:
        out["error"] = f"could not prefill from the campaign state ({exc})"
        return out


def npc_files():
    return sorted((CAMP_DIR / "info" / "npcs").glob("*.md"))


def npc_summary(path):
    secs = ntw.sections(path.read_text(encoding="utf-8"))
    char = secs.get("character", "")
    wav, kind = find_voice(path.stem)
    return {"slug": path.stem, "name": ntw.field(char, "name") or path.stem, "role": ntw.field(char, "role"),
            "disposition": ntw.field(char, "disposition") or "Neutral", "voice": (kind or "none").split(":")[0]}


def find_voice(slug):
    """(wav path, kind) for a locked voice, a generic stand-in from voice-overrides.json, or (None, None)."""
    dirs = [DATA / "website" / CAMP / "audio" / "introductions", DATA / "website" / "audio" / "introductions"]
    for d in dirs:
        if (d / f"{slug}.wav").exists():
            return d / f"{slug}.wav", "locked"
    generic = _overrides().get(slug)
    if generic and generic != "narrator":
        for d in dirs:
            if (d / f"{generic}.wav").exists():
                return d / f"{generic}.wav", f"generic:{generic}"
    return None, None


def _overrides():
    p = CAMP_DIR / "party" / "voice-overrides.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build_system_prompt(slug, scene):
    path = CAMP_DIR / "info" / "npcs" / f"{slug}.md"
    memory = CAMP_DIR / "party" / "npc-memory" / f"{slug}.md"
    body, intro, name = ntw.build(path, memory)
    spoken = ("\n\n## how you speak here\nThe party is talking to you in person at a table and your words are read aloud. "
              "Reply with only the words you say aloud: one to four short sentences, no stage directions, no asterisks, "
              "no narration, no quotation marks around your speech. Spelled-out sounds such as \"Ha!\" or \"Hrm.\" are fine. "
              "If you do not know something, say so in character. Several people are with you: every line starts with who is speaking "
              "(\"the half-elf paladin says: ...\" or a name). Answer the speaker, remember who said what, and use only the names "
              "and descriptions you are given: you do not know anyone's name until they have told it to you. Never invent a fact about a person, "
              "an item, a place or a past event. If you would plausibly know something that nothing above tells you (what an item does, who a named "
              "person is to you, where a place is), do not make it up and do not speak: reply with only a line that starts with NEED: followed by "
              "your question. If you would not know it, say so in character. "
              "Stay inside what the sources give you. Do not state a concrete detail that none of them gives: what something is made of, how old "
              "it is, where it came from, what it is worth, where someone is, what someone is doing or has done, how long something takes. "
              "You may describe what you can see in the scene as it is written there, and you may say you cannot tell or do not know. "
              "A vague true answer is better than a specific invented one.")
    scene_block = f"\n\n## the scene (from the DM; this is all you can perceive and all that has been approved for you to know)\n{scene.strip()}" if scene.strip() else ""
    return body.strip() + scene_block + spoken, name


def npc_log_path(slug):
    n = session_number()
    folder = CAMP_DIR / "party" / f"session-{n}"
    if not folder.is_dir():
        raise HTTPException(status_code=409, detail=f"Campaign session folder not found: {folder.relative_to(DATA)}. Check the campaign name and session number and try again.")
    seq = len(list(folder.glob(f"session-{n}-npc-*.md"))) + 1
    return n, folder / f"session-{n}-npc-{seq:02d}-{slug}.md"


def append(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


# ----------------------------------------------------------------------------------------------- the three models


def strip_reply(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"\*[^*\n]{0,200}\*", "", text)  # stage directions
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return text


async def llm_chat(messages, max_tokens=None, temperature=None):
    llm = CFG["llm"]
    if not llm.get("base_url"):
        raise HTTPException(status_code=503, detail="LLM address not configured (llm.base_url)")
    body = {"model": llm.get("model") or "default", "messages": messages, "max_tokens": max_tokens or llm["max_tokens"],
            "temperature": llm["temperature"] if temperature is None else temperature, **(llm.get("extra_body") or {})}
    headers = {"Authorization": f"Bearer {llm_key()}"} if llm_key() else {}
    async with httpx.AsyncClient(timeout=300) as c:
        try:
            r = await c.post(llm["base_url"].rstrip("/") + "/v1/chat/completions", json=body, headers=headers)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")
    return r.json()["choices"][0]["message"].get("content") or ""


async def warm_llm():
    """Load the model now (the Spark swaps models in on demand and a cold 27B takes minutes) while the DM sets the scene."""
    try:
        await llm_chat([{"role": "user", "content": "ok"}], max_tokens=1)
    except Exception:
        pass


async def stt(data, filename, content_type):
    async with httpx.AsyncClient(timeout=CFG["stt"]["timeout"]) as c:
        try:
            r = await c.post(CFG["stt"]["base_url"].rstrip("/") + "/v1/audio/transcriptions",
                             files={"file": (filename, data, content_type or "application/octet-stream")},
                             data={"response_format": "json"})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"speech-to-text request failed: {exc}")
    return (r.json().get("text") or "").strip()


def cached_transcript(wav):
    """The exact words of a reference clip that has no transcript file (player characters): transcribed once by the STT server and
    kept next to the tool, never in the campaign's website folder."""
    cache = HERE / ".transcripts" / f"{wav.stem}.txt"
    if cache.exists() and cache.read_text(encoding="utf-8").strip():
        return cache.read_text(encoding="utf-8").strip()
    try:
        r = httpx.post(CFG["stt"]["base_url"].rstrip("/") + "/v1/audio/transcriptions", files={"file": (wav.name, wav.read_bytes(), "audio/wav")},
                       data={"response_format": "json"}, timeout=60)
        r.raise_for_status()
        text = " ".join((r.json().get("text") or "").split())
    except Exception:
        return None
    if text:
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(text + "\n", encoding="utf-8")
    return text or None


def voice_for(slug):
    """(reference wav path, transcript or None) for an NPC, or (None, None)."""
    wav, kind = find_voice(slug)
    if not wav:
        return None, None
    if kind == "locked":
        side = wav.with_suffix(".txt")
        if side.exists() and side.read_text(encoding="utf-8").strip():
            return wav, side.read_text(encoding="utf-8").strip()
        npc = CAMP_DIR / "info" / "npcs" / f"{slug}.md"
        if npc.exists():
            return wav, ntw.intro_text(ntw.sections(npc.read_text(encoding="utf-8")).get("voice", "")) or None
        return wav, cached_transcript(wav)
    return wav, ntw.DEFAULT_INTRO  # a generic stand-in clip was read from the default introduction


def synth_blocking(slug, text):
    ref, transcript = voice_for(slug)
    if ref is None:
        return None
    tts = CFG["tts"]
    if tts["kind"] == "breeze":
        import urllib.request
        if not transcript:
            raise RuntimeError("Breeze needs the reference clip's exact transcript")
        body, ctype = breeze_multipart({"text": text, "ref_text": transcript, "seed": 42}, {"ref_audio": ("reference.wav", ref.read_bytes())})
        req = urllib.request.Request(tts["url"].rstrip("/") + "/v1/audio/speech", data=body, method="POST", headers={"Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=tts["timeout"]) as r:
            pcm = r.read()
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(pcm[: len(pcm) // 2 * 2])
        return out.getvalue()
    client = TTSServeClient(tts["url"], timeout=tts["timeout"])
    return client.synthesize(text, ref_wav=str(ref), ref_text=transcript, seed=None).wav


async def speak(slug, text):
    """Synthesize and finish one reply: returns WAV bytes, or None when the NPC has no voice."""
    wav = await asyncio.to_thread(synth_blocking, slug, text)
    return await asyncio.to_thread(finish_wav, wav, CFG["lead_in_s"]) if wav else None


async def _delayed_speak(slug, text, state):
    await asyncio.sleep(CFG["prefetch_delay_s"])  # the DM is reading; if they start editing, this is cancelled
    state["started"] = True
    return await speak(slug, text)


def start_prefetch(slug, text):
    global prefetch
    if not text or not conv:
        return
    state = {"started": False}
    task = asyncio.create_task(_delayed_speak(slug, text, state))
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # an abandoned job must not log "never retrieved"
    prefetch = {"slug": slug, "text": text, "task": task, "state": state}


async def drop_prefetch():
    """Forget a stale prefetch. Breeze serves one request at a time, so wait for it to finish; tts-serve engines accept
    parallel requests, so an edited reply does not have to wait for the unused one."""
    global prefetch
    if prefetch and not prefetch["state"]["started"]:
        prefetch["task"].cancel()  # still waiting its few seconds: nothing was spent on the GPU
    elif prefetch and CFG["tts"]["kind"] == "breeze":
        try:
            await prefetch["task"]
        except (Exception, asyncio.CancelledError):
            pass
    prefetch = None


def finish_wav(wav_bytes, lead_s):
    """Trim the engine's own leading and trailing silence, give every reply the same steady level, and put lead_s of
    silence in front (stdlib only: no numpy in the table-chat venv)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if width != 2 or n == 0:
            return wav_bytes
        raw = w.readframes(n)
    s = array.array("h")
    s.frombytes(raw)
    if sys.byteorder == "big":
        s.byteswap()
    if ch > 1:
        s = array.array("h", [s[i] for i in range(0, len(s), ch)])
    hop = max(1, rate // 100)
    rms = [math.sqrt(sum(x * x for x in s[i:i + hop]) / max(1, len(s[i:i + hop]))) for i in range(0, len(s), hop)]
    floor = 32768 * 10 ** (-60 / 20)
    loud = [i for i, r in enumerate(rms) if r > floor]
    if not loud:
        return wav_bytes
    start = max(0, loud[0] * hop - int(rate * 0.06))
    end = min(len(s), (loud[-1] + 1) * hop + int(rate * 0.15))
    s = s[start:end]
    # one gain for the whole reply: mean level of its speech frames to -20 dBFS, soft limiter
    frames = [math.sqrt(sum(x * x for x in s[i:i + rate // 10]) / max(1, len(s[i:i + rate // 10]))) for i in range(0, len(s), rate // 10)]
    db = [20 * math.log10(f / 32768 + 1e-9) for f in frames if f > 32768 * 10 ** (-45 / 20)]
    gain = 10 ** (((-20 - sum(db) / len(db)) if db else 0) / 20)
    out = array.array("h", [int(math.tanh(x / 32768 * gain / 0.9) * 0.9 * 32767) for x in s])
    out = array.array("h", [0] * int(rate * lead_s)) + out
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        data = out
        if sys.byteorder == "big":
            data = array.array("h", out)
            data.byteswap()
        w.writeframes(data.tobytes())
    return buf.getvalue()


# ----------------------------------------------------------------------------------------------- the conversation


def room_labels_fill():
    """Make sure every NPC in the room has a label for every party member and every other NPC (defaults, never overwriting)."""
    for slug in conv["order"]:
        have = conv["npcs"][slug]["labels"]
        for k, v in label_defaults(slug, conv["order"], conv["scene"]).items():
            have.setdefault(k, v)


def label_of(viewer, key):
    return conv["npcs"][viewer]["labels"].get(key) or ("the party" if key == "party" else key)


def linked_facts(slug, text):
    """What this NPC knows about the other NPCs named in `text`, tier by tier (npc_links.py --scene; DM-side secrets never appear)."""
    import subprocess
    try:
        out = subprocess.run([sys.executable, str(REPO / ".claude" / "scripts" / "npc_links.py"), CAMP, slug, "--scene", text],
                             cwd=DATA, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""
    lines = [l for l in out.splitlines() if l.startswith("- ") and "no other known NPC" not in l]
    return "\n".join(lines)


def system_for(slug, linked=""):
    """The NPC's prompt plus who else is in the room, in the words this NPC uses for them, plus what it is known to know."""
    n = conv["npcs"][slug]
    others = [label_of(slug, x) for x in conv["order"] if x != slug]
    room = ""
    if others:
        room = ("\n\n## who else is here\nAlso in the room with you: " + "; ".join(others) + ". They hear everything that is said. Their lines "
                "reach you as \"<who> says: ...\"; lines in brackets like \"(Narration: ...)\" describe what happens around you and are true. Speak only for yourself; answer when you are spoken to, or when you have something of your own to add.")
    known = [f["text"] for f in n.get("facts", [])]
    if linked:
        known = linked.splitlines() + known
    facts = ("\n\n## what you know about the people and things in play (from the DM's files; this is all you know about them)\n" +
             "\n".join(x if x.startswith("- ") else f"- {x}" for x in known)) if known else ""
    return n["base"] + room + facts


def heard_by(slug):
    """The history this NPC was present for: from when it joined, minus the stretches it was out of the room."""
    return [h for h in conv["history"][conv["npcs"][slug]["joined"]:] if slug in h.get("present", [slug])]


def history_for(slug, extra=None):
    """Chat messages as this NPC lived them: its own lines are the assistant's, everyone else's are user lines in its own words for them."""
    msgs = []
    def add(role, text):
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + text
        else:
            msgs.append({"role": role, "content": text})
    for h in heard_by(slug)[-CFG["history_turns"] * 3:]:
        if h["kind"] == "narration":
            add("user", f"(Narration: {h['text']})")
        elif h["kind"] == "npc":
            if h["slug"] == slug:
                add("assistant", h["text"])
            else:
                add("user", says(label_of(slug, h["slug"]), h["text"]))
        elif h["kind"] == "party":
            add("user", says(label_of(slug, h["key"]), h["text"]))
    if extra:
        add("user", extra)
    if msgs and msgs[0]["role"] == "assistant":
        msgs.insert(0, {"role": "user", "content": "(The conversation begins.)"})
    return msgs


CHIME_CUE = "(You have something to add to what was just said. Say it in one to four short sentences.)"


def pending_extra(pend, slug):
    if pend["kind"] == "line":
        return says(label_of(slug, pend["speaker"]), pend["party"])
    if pend.get("direction"):
        return f"(Cue from the DM: {pend['direction']}. Say it in your own words, one to four short sentences.)"
    return CHIME_CUE


def drop_echo(raw, name):
    """Models sometimes start by repeating the speaker line ("Caelith says: ...") or their own name. Remove those lines."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    own = re.compile(rf"^\W*{re.escape(name)}\W*$|^\W*{re.escape(name.split()[0])}\W*$", re.I)
    lines = [l for l in raw.splitlines() if l.strip() and not own.match(l.strip()) and not re.match(r"^[^:]{1,60}\bsays:", l.strip())]
    cleaned = "\n".join(lines)
    cleaned = re.sub(rf"^\W*(?:{re.escape(name)}|{re.escape(name.split()[0])})\s*:\s*", "", cleaned, flags=re.I)
    return cleaned or raw


NARRATOR_PROMPT = """You are the narrator of a fantasy tabletop roleplaying game. The DM reads your words aloud to the players. Write one to three
vivid sentences in the third person and present tense that describe what the party sees, hears and feels at this moment. Follow the
DM's DIRECTION; if there is none, describe a natural small beat that follows the conversation so far (someone shifts, a sound, the
light), advancing nothing important. Use only the SCENE, the TRANSCRIPT and the DIRECTION. Invent no secrets, no plot facts, no new
named people, and put no spoken words in anyone's mouth unless the DIRECTION gives them. Do not add any concrete detail about an
object (material, colour, age, markings, value), a place (layout, contents) or a person (clothing, build, injuries) that the SCENE,
the FACTS, the TRANSCRIPT or the DIRECTION does not give. Refer to things as the text does ("the ring", "the door"). Use only sensory generics
(heat, sound, light, movement) for atmosphere. Reply with the narration only.

SCENE: {scene}

FACTS THE DM HAS ESTABLISHED (you may use these details): {facts}

PEOPLE IN THE ROOM: {room}

TRANSCRIPT SO FAR (the last lines):
{transcript}

DIRECTION: {direction}"""


def public_transcript(n=10):
    out = []
    for h in conv["history"][-n:]:
        if h["kind"] == "narration":
            out.append(f"[Narration] {h['text']}")
        elif h["kind"] == "party":
            out.append(f"{speaker_name(h['key'])}: {h['text']}")
        else:
            out.append(f"{conv['npcs'][h['slug']]['display']}: {h['text']}")
    return "\n".join(out) or "(nothing has been said yet)"


async def draft_narration(pend, temperature=None):
    prompt = NARRATOR_PROMPT.format(scene=conv["scene"] or "(none)", facts=" ".join(conv.get("scene_facts", [])) or "(none)", room=", ".join(conv["npcs"][x]["display"] for x in conv["order"]),
                                    transcript=public_transcript(), direction=pend.get("direction") or "(none: choose a natural small beat)")
    raw = await llm_chat([{"role": "system", "content": "You write short, vivid narration."}, {"role": "user", "content": prompt}], max_tokens=200, temperature=temperature or 0.8)
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"^\W*narration\W*:\s*", "", text.replace("*", "").strip(), flags=re.I)).strip().strip('"')


async def draft_reply(pend, temperature=None):
    if pend["kind"] == "narration":
        return await draft_narration(pend, temperature)
    slug = pend["to"]
    name = conv["npcs"][slug]["name"]
    extra = pending_extra(pend, slug)
    if pend["kind"] == "line":
        extra += f"\n\n(Answer now as {name}: only your own spoken words, never repeating what was just said.)"
    context = " ".join([conv["scene"], pend.get("party", "")] + [h.get("text", "") for h in conv["history"][-6:]])
    linked = await asyncio.to_thread(linked_facts, slug, context)
    msgs = [{"role": "system", "content": system_for(slug, linked)}] + history_for(slug, extra)
    raw = await llm_chat(msgs, temperature=temperature)
    if re.match(r"^\W*NEED\b", raw.strip(), re.I):
        pend["need"] = re.sub(r"\s+", " ", re.sub(r"^\W*NEED\W*", "", raw.strip(), flags=re.I)).strip() or "(the NPC asked for a fact but did not say which)"
        return ""
    pend.pop("need", None)
    return strip_reply(drop_echo(raw, name))


async def run_draft(pend, temperature=None):
    """Draft for the waiting line. Only the newest request for this line may set the draft: an older call that finishes late (the DM
    asked again meanwhile) is dropped, and so is one for a line that is no longer waiting."""
    pend["seq"] = my = pend.get("seq", 0) + 1
    try:
        text = await draft_reply(pend, temperature)
        if pend.get("seq") != my or pending is not pend:
            return
        pend["draft"] = text
        if pend["draft"]:
            start_prefetch(pend["to"], pend["draft"])
    except HTTPException as exc:
        if pend.get("seq") != my or pending is not pend:
            return
        pend["draft"], pend["error"] = "", exc.detail
    await publish(["dm"], "pending", pend)


async def new_party_line(text, speaker="party"):
    """A line from the party (spoken, or typed by the DM): show it, draft the addressed NPC's answer for the DM."""
    global pending
    if not conv:
        raise HTTPException(status_code=409, detail="No conversation is active; the DM has to start one")
    if pending:
        raise HTTPException(status_code=409, detail="The DM has not answered the last line yet")
    if not conv["addressed"]:
        raise HTTPException(status_code=409, detail="Nobody is in the room to answer: bring an NPC back in, or use the narrator")
    pid = uuid.uuid4().hex[:8]
    name = speaker_name(speaker)
    pending = {"id": pid, "kind": "line", "party": text, "speaker": speaker, "speaker_name": name, "to": conv["addressed"],
               "to_name": conv["npcs"][conv["addressed"]]["display"], "draft": None}
    conv["lines"].append({"who": "party", "name": name, "text": text, "id": pid, "speaker": speaker})
    await publish(["table", "dm"], "line", conv["lines"][-1])
    await publish(["table"], "waiting", {"waiting": True})
    await publish(["dm"], "pending", pending)
    await run_draft(pending)
    return pending


# ----------------------------------------------------------------------------------------------- routes


@app.get("/")
async def table_page(t: str = ""):
    check_table(t)
    return FileResponse(HERE / "static" / "table.html")


@app.get("/dm")
async def dm_page(k: str = ""):
    check_dm(k)
    return FileResponse(HERE / "static" / "dm.html")


@app.get("/events")
async def events(role: str, k: str = "", t: str = ""):
    if role not in clients:
        raise HTTPException(status_code=400, detail="role must be table or dm")
    if role == "dm":
        check_dm(k)
    else:
        check_table(t, k)
    q = asyncio.Queue()
    clients[role].add(q)

    async def gen():
        yield sse("state", dm_state() if role == "dm" else public_state())
        try:
            while True:
                try:
                    yield await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            clients[role].discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/linevoice")
async def api_linevoice(body: dict, t: str = ""):
    """Speak a party line in the player character's own voice (on request, then kept). Tablet key."""
    check_table(t)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    line = next((l for l in conv["lines"] if l.get("id") == body.get("id") and l["who"] == "party"), None)
    if not line:
        raise HTTPException(status_code=404, detail="no such line")
    if line.get("audio"):
        return {"audio": line["audio"]}
    slug = line.get("speaker") or next((m["slug"] for m in party_members() if m["name"] == line["name"]), "party")
    if slug == "party" or not find_voice(slug)[0]:
        raise HTTPException(status_code=404, detail="this character has no voice")
    try:
        wav = await speak(slug, line["text"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"text-to-speech failed: {exc}")
    if not wav:
        raise HTTPException(status_code=404, detail="this character has no voice")
    aid = uuid.uuid4().hex[:10]
    await asyncio.to_thread(store_audio, aid, wav)
    await asyncio.to_thread(keep_audio, conv, line, wav)
    line["audio"] = f"/audio/{aid}.wav"
    save_state()
    return {"audio": line["audio"]}


def saved_conversations():
    out = []
    for lj in sorted((CAMP_DIR / "party").glob("session-*/*.audio/lines.json"), reverse=True):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        stem = lj.parent.name[:-len(".audio")]
        base = f"/saved/{lj.parent.parent.name}/{stem}"
        lines = [{**l, "url": f"{base}/{l['file']}" if l.get("file") else None} for l in d["lines"]]
        out.append({"id": f"{lj.parent.parent.name}/{stem}", "title": f"{stem.replace('-npc-', ' · ')}: {d.get('location', '')}", "session": d.get("session"), "lines": lines})
    return out


@app.get("/api/saved")
async def api_saved(x_dm_key: str = Header(default="")):
    """Every conversation whose recordings were kept, newest first, with each line's audio link."""
    check_dm(x_dm_key)
    return saved_conversations()


@app.get("/saved/{session}/{stem}/{file}")
async def saved_file(session: str, stem: str, file: str, k: str = ""):
    check_dm(k)
    if not (re.fullmatch(r"session-\d+", session) and re.fullmatch(r"[\w.-]+", stem) and re.fullmatch(r"[\w.-]+\.wav", file)):
        raise HTTPException(status_code=404)
    path = CAMP_DIR / "party" / session / f"{stem}.audio" / file
    if not path.is_file():
        raise HTTPException(status_code=404)
    return Response(content=path.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.get("/api/public")
async def api_public(t: str = ""):
    """The tablet's view of the conversation, for a tablet whose event stream has dropped (it polls this until the stream is back)."""
    check_table(t)
    return public_state()


@app.get("/audio/{aid}.wav")
async def get_audio(aid: str):
    path = AUDIO_DIR / f"{aid}.wav"
    if not re.fullmatch(r"[0-9a-f]{10}", aid) or not path.exists():
        raise HTTPException(status_code=404)
    return Response(content=path.read_bytes(), media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def health(x_dm_key: str = Header(default="")):
    check_dm(x_dm_key)
    out = {}
    async with httpx.AsyncClient(timeout=4) as c:
        for name, url in (("llm", (CFG["llm"].get("base_url") or "") + "/v1/models"), ("stt", CFG["stt"]["base_url"] + "/"),
                          ("tts", CFG["tts"]["url"] + ("/v1/model" if CFG["tts"]["kind"] == "breeze" else "/health"))):
            try:
                headers = {"Authorization": f"Bearer {llm_key()}"} if name == "llm" and llm_key() else {}
                r = await c.get(url, headers=headers)
                out[name] = "ok" if r.status_code < 500 else f"http {r.status_code}"
            except Exception:
                out[name] = "unreachable"
    out["session"] = session_number()
    out["api"] = API_LEVEL
    out["started"] = START_TS
    return out


@app.get("/api/npcs")
async def api_npcs(x_dm_key: str = Header(default="")):
    check_dm(x_dm_key)
    return [npc_summary(p) for p in npc_files()]


def add_to_room(slug, scene, labels=None, display=None):
    base, name = build_system_prompt(slug, scene)
    conv["npcs"][slug] = {"name": name, "display": (display or name).strip() or name, "base": base, "labels": dict(labels or {}),
                          "joined": len(conv["history"])}
    if slug not in conv["order"]:
        conv["order"].append(slug)


@app.post("/api/start")
async def api_start(body: dict, x_dm_key: str = Header(default="")):
    global conv, pending, prefetch
    check_dm(x_dm_key)
    if conv:
        raise HTTPException(status_code=409, detail="A conversation is already active; end it first")
    prefetch = None
    slug = body.get("slug", "")
    exists = lambda x: (CAMP_DIR / "info" / "npcs" / f"{x}.md").exists()
    if not exists(slug):
        raise HTTPException(status_code=404, detail="unknown NPC")
    scene = (body.get("scene") or "").strip()
    others = [x for x in (body.get("others") or []) if x != slug and exists(x)]
    n, log = npc_log_path(slug)
    asyncio.create_task(warm_llm())  # a cold model loads now, while the DM and players settle in
    summary = npc_summary(CAMP_DIR / "info" / "npcs" / f"{slug}.md")
    location = (body.get("location") or scene.split("\n")[0] or "[not given]").strip()
    name = npc_brief(slug)["name"]
    others_names = [npc_brief(x)["name"] for x in others]
    head = f"# Conversation Tracker: {name}\n**Session**: {n}\n**Campaign**: {CAMP}\n**Location**: {location}\n"
    if others_names:
        head += f"**Also present**: {', '.join(others_names)}\n"
    log.write_text(head + f"**NPC Disposition at start**: {summary['disposition']}\n\n---\n", encoding="utf-8")
    conv = {"main": slug, "addressed": slug, "order": [], "npcs": {}, "history": [], "scene": scene, "location": location, "session": n,
            "log": log, "lines": [], "exchange": 0, "id": uuid.uuid4().hex[:8]}
    labels_in, display_in = body.get("labels") or {}, body.get("display") or {}
    for x in [slug] + others:
        add_to_room(x, scene, (labels_in.get(x) if isinstance(labels_in.get(x), dict) else None), display_in.get(x))
    room_labels_fill()
    pending = None
    await publish(["table", "dm"], "state", public_state())
    await publish(["dm"], "state", dm_state())
    return dm_state()


@app.post("/api/utterance")
async def api_utterance(audio: UploadFile = File(...), speaker: str = Form(default="party"), t: str = ""):
    """The tablet's recording. Tablet key."""
    check_table(t)
    data = await audio.read()
    if len(data) < 800:
        return {"ignored": "too short"}
    await publish(["table"], "status", {"text": "Listening to what you said…"})
    text = await stt(data, audio.filename or "audio.webm", audio.content_type)
    if len(text) < 2:
        await publish(["table"], "status", {"text": "I did not catch that. Hold the button and try again."})
        return {"ignored": "nothing heard"}
    p = await new_party_line(text, speaker)
    return {"text": text, "id": p["id"], "speaker": p["speaker_name"]}


@app.post("/api/say")
async def api_say(body: dict, x_dm_key: str = Header(default="")):
    check_dm(x_dm_key)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty line")
    return await new_party_line(text, body.get("speaker") or "party")


def party_text(pend):
    if pend["kind"] == "chime":
        return f"*(no new line; {conv['npcs'][pend['to']]['name']} adds to the conversation)*"
    said = pend["party"] if pend["speaker"] == "party" else f"{pend['speaker_name']}: {pend['party']}"
    return f"(to {conv['npcs'][pend['to']]['name']}) {said}" if len(conv["order"]) > 1 else said


@app.post("/api/regenerate")
async def api_regenerate(body: dict = None, x_dm_key: str = Header(default="")):
    check_dm(x_dm_key)
    if not pending:
        raise HTTPException(status_code=409, detail="nothing is waiting")
    body = body or {}
    fixed = (body.get("party") or "").strip()
    if pending["kind"] == "line" and fixed and fixed != pending["party"]:  # the DM corrected the transcription
        pending["party"] = fixed
        for line in reversed(conv["lines"]):
            if line.get("id") == pending["id"] and line["who"] == "party":
                line["text"] = fixed
                break
        await publish(["table"], "state", public_state())
    to = body.get("to")
    if pending["kind"] != "narration" and to and to in conv["npcs"] and to != pending["to"]:
        pending["to"], pending["to_name"] = to, conv["npcs"][to]["display"]
        if pending["kind"] == "line":
            conv["addressed"] = to
            await publish(["table", "dm"], "state", public_state())
    if pending["kind"] in ("narration", "chime") and "direction" in body:
        pending["direction"] = (body.get("direction") or "").strip()
    pending["draft"] = None
    pending.pop("error", None)
    await publish(["dm"], "pending", pending)
    await drop_prefetch()
    await run_draft(pending, temperature=0.95)
    return pending


@app.post("/api/approve")
async def api_approve(body: dict, x_dm_key: str = Header(default="")):
    """The DM's final text is spoken, shown on the tablet and logged. Not the draft: the DM's edit."""
    global pending, prefetch
    check_dm(x_dm_key)
    if not (conv and pending):
        raise HTTPException(status_code=409, detail="nothing is waiting")
    if pending.get("need"):
        raise HTTPException(status_code=409, detail="Answer what the NPC needs to know first (or say it does not know)")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty reply")
    slug = pending["to"]
    n = conv["npcs"][slug] if slug in conv["npcs"] else {"name": "Narrator", "display": "Narrator"}
    aid = None
    kept = None
    warning = None
    try:
        if prefetch and prefetch["text"] == text and prefetch["slug"] == slug:
            done = await prefetch["task"]  # already synthesized (or nearly) while the DM read the draft
            prefetch = None
        else:
            await drop_prefetch()
            done = await speak(slug, text)
        if done:
            aid = uuid.uuid4().hex[:10]
            await asyncio.to_thread(store_audio, aid, done)
            kept = done
        else:
            warning = "this NPC has no voice yet: shown as text only"
    except Exception as exc:  # the line still goes out as text
        warning = f"text-to-speech failed ({exc}); shown as text only"
    if pending["kind"] == "narration":
        append(conv["log"], f"\n*[Narration]*: {text}\n\n---\n")
        conv["history"].append({"kind": "narration", "text": text, "present": list(conv["order"])})
    else:
        conv["exchange"] += 1
        append(conv["log"], f"\n## Exchange {conv['exchange']}\n\n**Party**: {party_text(pending)}\n\n**{n['name']}**: {text}\n\n---\n")
        if pending["kind"] == "line":
            conv["history"].append({"kind": "party", "key": pending["speaker"], "text": pending["party"], "present": list(conv["order"])})
        conv["history"].append({"kind": "npc", "slug": slug, "text": text, "present": list(conv["order"])})
    line = {"who": "narrator" if pending["kind"] == "narration" else "npc", "name": n["display"], "slug": slug, "text": text, "audio": f"/audio/{aid}.wav" if aid else None, "id": pending["id"]}
    conv["lines"].append(line)
    if aid:
        await asyncio.to_thread(keep_audio, conv, line, kept)
    else:
        save_lines(conv)
    pending = None
    await publish(["table", "dm"], "reply", line)
    await publish(["table"], "waiting", {"waiting": False})
    await publish(["dm"], "pending", None)
    await publish(["dm"], "state", dm_state())
    return {"ok": True, "warning": warning, "exchange": conv["exchange"]}


@app.post("/api/skip")
async def api_skip(x_dm_key: str = Header(default="")):
    global pending
    check_dm(x_dm_key)
    if not (conv and pending):
        raise HTTPException(status_code=409, detail="nothing is waiting")
    await drop_prefetch()
    if pending["kind"] == "narration":  # the DM did not want it: nothing is logged
        pending = None
        await publish(["table"], "waiting", {"waiting": False})
        await publish(["dm"], "pending", None)
        return {"ok": True}
    conv["exchange"] += 1
    n = conv["npcs"][pending["to"]]
    append(conv["log"], f"\n## Exchange {conv['exchange']}\n\n**Party**: {party_text(pending)}\n\n**{n['name']}**: *(no response)*\n\n---\n")
    if pending["kind"] == "line":
        conv["history"].append({"kind": "party", "key": pending["speaker"], "text": pending["party"], "present": list(conv["order"])})
    pending = None
    await publish(["table"], "waiting", {"waiting": False})
    await publish(["dm"], "pending", None)
    await publish(["dm"], "state", dm_state())
    return {"ok": True}


@app.post("/api/withdraw")
async def api_withdraw(x_dm_key: str = Header(default="")):
    """Take back the waiting line (a mistake or a wrong tool): it disappears from the tablet and nothing is logged or remembered."""
    global pending
    check_dm(x_dm_key)
    if not (conv and pending):
        raise HTTPException(status_code=409, detail="nothing is waiting")
    await drop_prefetch()
    conv["lines"] = [l for l in conv["lines"] if l.get("id") != pending["id"]]
    pending = None
    await publish(["table", "dm"], "state", public_state())
    await publish(["table"], "waiting", {"waiting": False})
    await publish(["dm"], "pending", None)
    await publish(["dm"], "state", dm_state())
    return {"ok": True}


@app.post("/api/amend")
async def api_amend(body: dict, x_dm_key: str = Header(default="")):
    """Correct a wrong detail in what was already said: the replacement is made in the log, the tablet's chat, the saved text and what
    the NPCs remember hearing. (Recordings already made keep the old words.)"""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    old, new = body.get("find") or "", body.get("replace") or ""
    if not old:
        raise HTTPException(status_code=400, detail="nothing to find")
    changed = 0
    for coll in (conv["lines"], conv["history"]):
        for e in coll:
            if old in e.get("text", ""):
                e["text"] = e["text"].replace(old, new)
                changed += 1
    log = conv["log"].read_text(encoding="utf-8")
    if old in log:
        conv["log"].write_text(log.replace(old, new), encoding="utf-8")
        changed += 1
    save_lines(conv)
    await publish(["table", "dm"], "state", public_state())
    await publish(["dm"], "state", dm_state())
    if not changed:
        raise HTTPException(status_code=404, detail="that text was not found")
    return {"changed": changed}


def tell_fact(to, fact, basis, remember=False):
    """Give `fact` to one NPC in the room, or to everyone present ("room"), and note it with its basis in the log."""
    if to == "room":
        targets = list(conv["order"])
        conv.setdefault("scene_facts", []).append(fact)
    elif to in conv["order"]:
        targets = [to]
    else:
        raise HTTPException(status_code=404, detail="that NPC is not in the room")
    for t in targets:
        conv["npcs"][t].setdefault("facts", []).append({"text": fact, "lasting": bool(remember)})
    who = "everyone present" if to == "room" else conv["npcs"][to]["name"]
    append(conv["log"], f"\n*[DM fact for {who}: {fact} (basis: {basis})]*\n\n---\n")
    return [conv["npcs"][t]["name"] for t in targets]


@app.post("/api/tell")
async def api_tell(body: dict, x_dm_key: str = Header(default="")):
    """Give an NPC a fact before it has to ask: what an item is made of, what someone knows. `to` is an NPC slug, or "room" for a fact
    everyone present can see (the narrator may use it too). A basis (why the NPC would know it) is required and logged. `remember` also
    saves it to the NPC's memory when the conversation ends."""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    fact, to, basis = (body.get("fact") or "").strip(), body.get("to") or "room", (body.get("basis") or "").strip()
    if not fact:
        raise HTTPException(status_code=400, detail="empty fact")
    if not basis:
        raise HTTPException(status_code=400, detail="say why the NPC would know this (it can see it, its files say so, the DM ruled it): an NPC is never told a fact without a basis")
    told = tell_fact(to, fact, basis, body.get("remember"))
    await publish(["dm"], "state", dm_state())
    return {"told": told}


LOOK_PROMPT = """Below is the description of an object from a campaign's object ledger. Write what someone who is HOLDING the object in their hands
can see of it: colour, material only if the text states it, size, shape, cut, markings or the lack of them, condition. One or two plain sentences.
Leave out: where it was found, who owned or carried it, what it is worth or was appraised at, its history, its grade, rank, purpose or
meaning, anything magical or hidden (unless the text says it is plainly visible), and anything about the party. A description such as
"an old-cut ruby ring" is a look and counts: keep the words that describe how it looks. Use only what the text says; invent nothing. If the text gives
no physical look at all, reply with exactly NONE.

OBJECT: {name}
DESCRIPTION:
{text}"""


def object_file(ref):
    folder = CAMP_DIR / "party" / "objects"
    exact = folder / f"{ref}.md"
    if exact.is_file():
        return exact
    key = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
    hits = [p for p in folder.glob("*.md") if key and (key in p.stem or p.stem in key)]
    return hits[0] if len(hits) == 1 else None


@app.post("/api/give")
async def api_give(body: dict, x_dm_key: str = Header(default="")):
    """An object changes hands: tell the NPC (or everyone present) only what can be SEEN of it, taken from the object's ledger entry.
    `look` is the DM's own description and replaces the ledger. The ledger text is party-view and may include history or value, so a model
    pass keeps only the physical look; if the ledger gives none, the DM must supply `look`."""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    to, ref, look = body.get("to") or "room", (body.get("object") or "").strip(), (body.get("look") or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="which object?")
    path = object_file(ref)
    name = (re.search(r"^# (.+)$", path.read_text(encoding="utf-8"), re.M).group(1).strip() if path else ref)
    if not look:
        if not path:
            raise HTTPException(status_code=404, detail=f"no object ledger entry matches '{ref}': give the look yourself (--look)")
        text = path.read_text(encoding="utf-8")
        m = re.search(r"^## Description\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
        what = re.search(r"\*\*What it is\*\*:\s*(.+)", text)
        desc = ((what.group(1) + "\n\n") if what else "") + (m.group(1) if m else text.split("## Ledger")[0]).strip()
        raw = await llm_chat([{"role": "system", "content": "You extract only what is visible, and invent nothing."}, {"role": "user", "content": LOOK_PROMPT.format(name=name, text=desc)}], max_tokens=200, temperature=0.1)
        look = re.sub(r"\s+", " ", re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)).strip().strip('"')
        if not look or look.upper().startswith("NONE"):
            raise HTTPException(status_code=422, detail=f"the ledger entry for '{name}' gives no physical look: give it yourself (--look)")
    told = tell_fact(to, f"The {name.split(' (')[0].lower()} that has been handed over: {look}", "the object is in view and in hand", False)
    await publish(["dm"], "state", dm_state())
    return {"told": told, "object": name, "look": look}


@app.post("/api/address")
async def api_address(body: dict, x_dm_key: str = Header(default="")):
    """The DM switches who the party is talking to. The next line is answered by that NPC."""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    to = body.get("to")
    if to not in conv["npcs"]:
        raise HTTPException(status_code=404, detail="that NPC is not in the room")
    conv["addressed"] = to
    await publish(["table", "dm"], "state", public_state())
    await publish(["dm"], "state", dm_state())
    return {"addressed": to}


@app.post("/api/chime")
async def api_chime(body: dict, x_dm_key: str = Header(default="")):
    """Another NPC in the room speaks up, with no new line from the party. Drafted for the DM like any reply."""
    global pending
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    if pending:
        raise HTTPException(status_code=409, detail="The DM has not answered the last line yet")
    to = body.get("to")
    if to not in conv["npcs"]:
        raise HTTPException(status_code=404, detail="that NPC is not in the room")
    pending = {"id": uuid.uuid4().hex[:8], "kind": "chime", "direction": (body.get("direction") or "").strip(), "party": "", "speaker": "party", "speaker_name": "", "to": to,
               "to_name": conv["npcs"][to]["display"], "draft": None}
    await publish(["table"], "waiting", {"waiting": True})
    await publish(["dm"], "pending", pending)
    await run_draft(pending)
    return pending


@app.post("/api/answer")
async def api_answer(body: dict, x_dm_key: str = Header(default="")):
    """The DM answers an NPC's NEED (a fact it should know but the files do not give): the answer joins what that NPC knows for the
    rest of the conversation and is saved to its memory under Linked knowledge. `unknown: true` tells it to play honest ignorance."""
    check_dm(x_dm_key)
    if not (conv and pending and pending.get("need")):
        raise HTTPException(status_code=409, detail="nothing is asking for a fact")
    n = conv["npcs"][pending["to"]]
    if body.get("unknown"):
        n.setdefault("facts", []).append({"text": f"You do not know this: {pending['need']} Play honest ignorance in character.", "lasting": False})
    else:
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="empty answer")
        n.setdefault("facts", []).append({"text": text, "lasting": True})
    pending["draft"] = None
    pending.pop("need", None)
    pending.pop("error", None)
    await publish(["dm"], "pending", pending)
    await run_draft(pending)
    return pending


@app.post("/api/narrate")
async def api_narrate(body: dict, x_dm_key: str = Header(default="")):
    """The narrator describes something between the lines (a pause, someone leaving or returning, the room). Drafted for the DM
    like any reply; once approved it is shown, spoken in the narrator's voice, logged, and heard by everyone in the room."""
    global pending
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    if pending:
        raise HTTPException(status_code=409, detail="The DM has not answered the last line yet")
    pending = {"id": uuid.uuid4().hex[:8], "kind": "narration", "direction": (body.get("direction") or "").strip(), "party": "", "speaker": "party",
               "speaker_name": "", "to": "narrator", "to_name": "Narrator", "draft": None}
    await publish(["dm"], "pending", pending)
    await run_draft(pending)
    return pending


@app.post("/api/room")
async def api_room(body: dict, x_dm_key: str = Header(default="")):
    """Someone walks in or leaves. A newcomer knows nothing of what was said before (it starts hearing from now on); a leaver is
    kept in the records, because they were present for what they heard."""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    if pending:
        raise HTTPException(status_code=409, detail="answer the waiting line first")
    add, drop = body.get("add"), body.get("remove")
    if add:
        if add in conv["order"] or not (CAMP_DIR / "info" / "npcs" / f"{add}.md").exists():
            raise HTTPException(status_code=409, detail="that NPC is already here or unknown")
        if add in conv["npcs"]:  # someone who stepped out comes back: they remember what they heard before leaving
            conv["npcs"][add].pop("left", None)
            conv["order"].append(add)
            conv["left"] = [x for x in conv.get("left", []) if x != add]
        else:
            add_to_room(add, conv["scene"], display=body.get("display"))
        room_labels_fill()
        append(conv["log"], f"\n*[{conv['npcs'][add]['name']} joins the conversation]*\n\n---\n")
    if drop:
        if drop not in conv["order"]:
            raise HTTPException(status_code=409, detail="that NPC is not in the room")
        conv["order"].remove(drop)
        conv["npcs"][drop]["left"] = True
        for o in conv["order"]:
            conv["npcs"][o]["labels"].pop(drop, None)
        conv["left"] = conv.get("left", []) + [drop]
        if conv["addressed"] == drop:
            conv["addressed"] = conv["order"][0] if conv["order"] else None
        append(conv["log"], f"\n*[{conv['npcs'][drop]['name']} leaves the conversation]*\n\n---\n")
    await publish(["table", "dm"], "state", public_state())
    await publish(["dm"], "state", dm_state())
    return dm_state()


@app.get("/api/pcs")
async def api_pcs(npc: str = "", scene: str = "", x_dm_key: str = Header(default=""), t: str = ""):
    """The party's characters. Names and descriptions only for the tablet; with the DM key and an NPC, also the label the NPC would use."""
    check_table(t, x_dm_key)
    members = party_members()
    if npc and x_dm_key:
        check_dm(x_dm_key)
        labels = default_labels(npc, scene)
        return [{**m, "label": labels.get(m["slug"], m["short"])} for m in members]
    return [{"slug": m["slug"], "name": m["name"], "short": m["short"]} for m in members]


@app.post("/api/labels/suggest")
async def api_labels_suggest(body: dict, x_dm_key: str = Header(default="")):
    """Prefill the label grid for a set of NPCs: for each NPC, how it refers to every party member and each other NPC in the room."""
    check_dm(x_dm_key)
    scene = body.get("scene", "")
    room = [x for x in [body.get("slug")] + list(body.get("others") or []) if x and (CAMP_DIR / "info" / "npcs" / f"{x}.md").exists()]
    async def one(v):
        return v, await refine_labels(v, label_defaults(v, room, scene), room, scene)
    got = dict(await asyncio.gather(*[one(v) for v in room]))
    return {"labels": got, "names": {x: npc_brief(x)["name"] for x in room}}


@app.post("/api/labels")
async def api_labels(body: dict, x_dm_key: str = Header(default="")):
    """The DM changes how an NPC refers to someone (for example after they introduce themselves), or the name the party sees."""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    for viewer, labs in (body.get("labels") or {}).items():
        if viewer in conv["npcs"] and isinstance(labs, dict):
            for k, v in labs.items():
                if k in conv["npcs"][viewer]["labels"] and str(v).strip():
                    conv["npcs"][viewer]["labels"][k] = str(v).strip()
    for slug, d in (body.get("display") or {}).items():
        if slug in conv["npcs"] and str(d).strip():
            conv["npcs"][slug]["display"] = str(d).strip()
    await publish(["table", "dm"], "state", public_state())
    await publish(["dm"], "state", dm_state())
    return {x: conv["npcs"][x]["labels"] for x in conv["npcs"]}


@app.post("/api/editing")
async def api_editing(x_dm_key: str = Header(default="")):
    """The DM began editing the draft: if it has not been spoken yet, do not waste the GPU on it."""
    check_dm(x_dm_key)
    await drop_prefetch()
    return {"ok": True}


@app.post("/api/restart")
async def api_restart(x_dm_key: str = Header(default="")):
    """Start the same conversation over: same NPCs, scene, labels and log file, but the log is cut back to its header and every
    NPC forgets what was said (nothing is written to any memory file)."""
    global pending, prefetch
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    await drop_prefetch()
    prefetch = None
    main = conv["main"]
    head = f"# Conversation Tracker: {conv['npcs'][main]['name']}\n**Session**: {conv['session']}\n**Campaign**: {CAMP}\n**Location**: {conv['location']}\n"
    others = [conv["npcs"][x]["name"] for x in conv["npcs"] if x != main]
    if others:
        head += f"**Also present**: {', '.join(others)}\n"
    conv["log"].write_text(head + f"**NPC Disposition at start**: {npc_summary(CAMP_DIR / 'info' / 'npcs' / f'{main}.md')['disposition']}\n\n---\n", encoding="utf-8")
    shutil.rmtree(audio_folder(conv), ignore_errors=True)
    conv["scene_facts"] = []
    for x in conv["npcs"].values():
        x["facts"] = []
    conv.update({"aseq": 0, "history": [], "lines": [], "exchange": 0, "left": [], "order": list(conv["npcs"]), "addressed": main, "id": uuid.uuid4().hex[:8]})
    for x in conv["npcs"].values():
        x["joined"] = 0
        x.pop("left", None)
    pending = None
    await publish(["table", "dm"], "state", public_state())
    await publish(["table"], "waiting", {"waiting": False})
    await publish(["dm"], "state", dm_state())
    return dm_state()


@app.post("/api/stop")
async def api_stop(x_dm_key: str = Header(default="")):
    check_dm(x_dm_key)
    await publish(["table"], "stop", {})
    return {"ok": True}


END_PROMPT = """Below is a conversation in which a party of adventurers speaks with the NPC {name}{room}. Write the NPC's own record of it as JSON
with exactly these keys: "final_disposition" (one of Hostile, Suspicious, Neutral, Warming, Friendly, Allied), "revealed" (list of
facts the NPC told the party), "withheld" (list of things the NPC knew but did not say), "commitments" (list of promises or
deals by either side, or []), "next_beat" (one or two sentences: what the NPC expects or does next), "learned" (list of things
the NPC learned from the party), "told" (short list of what the NPC told the party). Use only what is in the conversation and the
NPC's own file below; invent nothing. Refer to everyone exactly as the transcript labels them (the NPC may not know
their names). Reply with the JSON object only.

NPC DISPOSITION AT START: {start}

CONVERSATION:
{transcript}"""


def transcript_for(slug):
    out = []
    for h in heard_by(slug):
        if h["kind"] == "narration":
            out.append(f"NARRATION: {h['text']}")
        elif h["kind"] == "party":
            out.append(f"{label_of(slug, h['key']).upper()}: {h['text']}")
        elif h["slug"] == slug:
            out.append(f"{conv['npcs'][slug]['name'].upper()}: {h['text']}")
        else:
            out.append(f"{label_of(slug, h['slug']).upper()}: {h['text']}")
    return "\n".join(out)


def everyone():
    """Slugs that were in the conversation: those still here and those who left."""
    return conv["order"] + [x for x in conv.get("left", []) if x not in conv["order"]]


async def draft_end(slug):
    """The closing record for one NPC, drafted from what it heard, in its own terms. Nothing is written."""
    transcript = transcript_for(slug)
    draft = {"final_disposition": "Neutral", "revealed": [], "withheld": [], "commitments": [], "next_beat": "", "learned": [], "told": []}
    if transcript:
        try:
            others = [label_of(slug, x) for x in conv["order"] if x != slug]
            raw = await llm_chat([{"role": "system", "content": "You write careful, factual records."},
                                  {"role": "user", "content": END_PROMPT.format(name=conv["npcs"][slug]["name"], room=(f" (also present: {', '.join(others)})" if others else ""),
                                                                                start=npc_summary(CAMP_DIR / "info" / "npcs" / f"{slug}.md")["disposition"], transcript=transcript)}],
                                 max_tokens=700, temperature=0.2)
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                raise ValueError("no JSON in the answer")
            draft.update({k: v for k, v in json.loads(m.group(0)).items() if k in draft})
        except Exception as exc:
            draft["_error"] = f"could not draft the summary ({exc}); fill it in by hand"
    draft["location"] = conv["location"]
    draft["name"] = conv["npcs"][slug]["name"]
    draft["heard"] = bool(transcript)
    return draft


async def draft_all():
    slugs = everyone()
    return dict(zip(slugs, await asyncio.gather(*[draft_end(x) for x in slugs])))


@app.post("/api/end")
async def api_end(x_dm_key: str = Header(default="")):
    """Draft the closing records (one per NPC in the room) for the DM to review. Nothing is written until the DM confirms."""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    return {"main": conv["main"], "drafts": await draft_all()}


@app.post("/api/end/auto")
async def api_end_auto(x_dm_key: str = Header(default="")):
    """One step: draft the closing records and save them. Falls back to the review form when nothing was said or drafting failed."""
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    drafts = await draft_all()
    if not conv["exchange"]:
        return {"needs_review": True, "reason": "nothing was answered in this conversation yet", "main": conv["main"], "drafts": drafts}
    bad = [d["_error"] for d in drafts.values() if d.get("_error")]
    if bad:
        return {"needs_review": True, "reason": bad[0], "main": conv["main"], "drafts": drafts}
    return {"saved": await write_end(drafts)}


def _bullets(items):
    items = [i for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {i}" for i in items) if items else "- None"


@app.post("/api/end/discard")
async def api_end_discard(body: dict = None, x_dm_key: str = Header(default="")):
    """End the conversation without writing a Conversation End block or a memory entry. The log keeps the exchanges so far,
    unless the DM also asks for it to be deleted."""
    global conv, pending
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    await drop_prefetch()
    deleted = False
    if (body or {}).get("delete_log"):
        try:
            conv["log"].unlink()
            deleted = True
        except OSError:
            pass
        shutil.rmtree(audio_folder(conv), ignore_errors=True)
    else:
        asyncio.create_task(finalize_audio(conv))
    info = {"log": str(conv["log"].relative_to(DATA)), "deleted": deleted, "exchanges": conv["exchange"]}
    conv, pending = None, None
    await publish(["table", "dm"], "state", public_state())
    return info


def write_memory(slug, name, session, body, location, facts=()):
    mem = CAMP_DIR / "party" / "npc-memory" / f"{slug}.md"
    join = lambda items: "; ".join(str(i).strip() for i in (items or []) if str(i).strip()) or "nothing"
    disp = body.get("final_disposition") or "Neutral"
    entry = (f"### Session {session} — {body.get('location') or location}\n"
             f"- **Learned from the party**: {join(body.get('learned'))}\n- **Told the party**: {join(body.get('told') or body.get('revealed'))}\n"
             f"- **Withheld / lied about**: {join(body.get('withheld'))}\n- **Commitments**: {join(body.get('commitments'))}\n"
             f"- **Disposition after**: {disp}\n")
    if not mem.exists():
        mem.parent.mkdir(parents=True, exist_ok=True)
        mem.write_text(f"# NPC memory: {name} ({slug})\n\n_What this NPC knows from conversations with the party. Appended at the end of every conversation._\n\n"
                       "## What they know about the party\n- (add names and faces from the conversation history)\n\n## Conversation history\n\n"
                       "## Linked knowledge\n\n## Third-party information (DM-approved)\n- (none recorded)\n\n## Waiting for / open\n- \n", encoding="utf-8")
    text = mem.read_text(encoding="utf-8")
    marker = "\n## Linked knowledge"
    text = text.replace(marker, "\n" + entry + marker, 1) if marker in text else text.rstrip("\n") + "\n\n" + entry
    if facts:
        bullets = "".join(f"- (Session {session}, DM answer) {f}\n" for f in facts)
        m = re.search(r"^## Linked knowledge[^\n]*\n", text, re.M)
        text = text[:m.end()] + bullets + text[m.end():] if m else text.rstrip("\n") + "\n\n## Linked knowledge\n" + bullets
    mem.write_text(text, encoding="utf-8")
    return str(mem.relative_to(DATA))


async def write_end(records):
    """Append the Conversation End block(s) to the log and a Session entry to each NPC's memory file; close the conversation.
    `records` maps NPC slug to its record. The main NPC's block is the standard one; the others get a named block."""
    global conv, pending
    memories = []
    for slug in everyone():
        body = records.get(slug)
        if body is None or (slug != conv["main"] and not body.get("heard", True)):
            continue
        name = conv["npcs"][slug]["name"]
        disp = body.get("final_disposition") or "Neutral"
        title = "Conversation End" if slug == conv["main"] else f"Conversation End: {name}"
        append(conv["log"], f"\n## {title}\n\n**Final disposition**: {disp}\n\n**Information revealed**:\n{_bullets(body.get('revealed'))}\n\n"
                            f"**Information withheld**:\n{_bullets(body.get('withheld'))}\n\n**Commitments made**:\n{_bullets(body.get('commitments'))}\n\n"
                            f"**Next beat**:\n{(body.get('next_beat') or '').strip() or 'None recorded.'}\n")
        memories.append(write_memory(slug, name, conv["session"], body, conv["location"], [f["text"] for f in conv["npcs"][slug].get("facts", []) if f.get("lasting")]))
    done = {"log": str(conv["log"].relative_to(DATA)), "memory": memories[0] if memories else None, "memories": memories, "exchanges": conv["exchange"]}
    asyncio.create_task(finalize_audio(conv))
    conv, pending = None, None
    await publish(["table", "dm"], "state", public_state())
    return done


@app.post("/api/end/confirm")
async def api_end_confirm(body: dict, x_dm_key: str = Header(default="")):
    check_dm(x_dm_key)
    if not conv:
        raise HTTPException(status_code=409, detail="no active conversation")
    return await write_end(body.get("records") or {conv["main"]: body})


async def redraft_after_restart():
    """A restart interrupted the model call for the pending line: ask again."""
    await run_draft(pending)


@app.on_event("startup")
async def announce():
    resumed = load_state()
    if resumed and pending and pending.get("draft") is None and not pending.get("error"):
        asyncio.create_task(redraft_after_restart())
    port = CFG["port"]
    pub = (CFG.get("public") or {}).get("base_url")
    public_line = f"  tablet (public): {pub.rstrip('/')}/{CAMP}/chat/?t={TABLE_KEY}\n" if pub else ""
    print(f"\nTable chat for {CAMP} (session {session_number()})\n  tablet: http://127.0.0.1:{port}/?t={TABLE_KEY}\n{public_line}  DM:     http://127.0.0.1:{port}/dm?k={DM_KEY}\n"
          f"  LLM {CFG['llm'].get('base_url')} | STT {CFG['stt']['base_url']} | TTS {CFG['tts']['kind']} {CFG['tts']['url']}\n", flush=True)
    if resumed:
        print(f"  resumed the conversation with {conv['npcs'][conv['main']]['name']} ({conv['exchange']} exchanges so far)\n", flush=True)
