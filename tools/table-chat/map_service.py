"""The standalone map: the "Table Maps" page (battle map and city map) served by the table chat server.

The two map pages were written against a small page runtime: `claude.use("db")` (documents and collections with snapshots),
`claude.use("user")` (who may edit) and `claude.use("assets")` (uploaded images, shown from `/_blob/<id>`). This module
is a small local stand-in for exactly that surface, so the pages run unchanged and need nothing published anywhere:

  documents      campaigns/<campaign>/party/maps/db.json   {"docs": {path: data}, "rev": {path: n}}
  assets         campaigns/<campaign>/party/maps/assets.json   {id: {name, file, mime}} (the files stay where they are)
  live updates   /map/_events (server-sent events), the page's shim (static/map-shim.js) turns them into onSnapshot calls

Roles come from the keys the server already has: the DM key is `admin`, the tablet key is `interact`. The access rules are
these (dm: admin; table: read view, write admin; moves: interact; city: admin; citypub: read view,
write admin; citypins: read view, write admin, plus a player's own `citypins/<id>` for interact).

Claude reaches the same documents through the MCP tools `map_*` (mcp_server.py), which call `/map/_doc` with the DM key.
Nothing here runs on its own: server.py includes `router` and calls `init()`.
"""
import asyncio
import json
import mimetypes
import re
import secrets
import struct
import time
from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse

router = APIRouter()
CFG = {}  # filled by init()

RANK = {"view": 1, "interact": 2, "admin": 3}
RULES = {  # first path segment -> (read, write)
    "dm": ("admin", "admin"), "table": ("view", "admin"), "moves": ("interact", "interact"),
    "city": ("admin", "admin"), "citypub": ("view", "admin"), "citypins": ("view", "admin"),
}
MAX_DOC = 6_000_000  # bytes of JSON in one document


def init(camp_dir, repo, dm_key, table_key, page_file):
    """camp_dir: campaigns/<campaign>; dm_key / table_key: the server's two keys; page_file: the combined page to serve."""
    root = Path(camp_dir) / "party" / "maps"
    root.mkdir(parents=True, exist_ok=True)
    CFG.update(camp=Path(camp_dir), repo=Path(repo), root=root, dm=dm_key, table=table_key, page=Path(page_file),
               here=Path(__file__).resolve().parent)
    STORE.load()
    ASSETS.load()


# ----------------------------------------------------------------------------------------------- access


def role_of(k="", t=""):
    if k and secrets.compare_digest(k, CFG["dm"]):
        return "admin"
    if t and secrets.compare_digest(t, CFG["table"]):
        return "interact"
    return None


def need_role(k="", t="", x_dm_key="", x_table_key=""):
    role = role_of(k or x_dm_key, t or x_table_key)
    if not role:
        raise HTTPException(status_code=403, detail="Map key missing or wrong (DM key ?k= or tablet key ?t=)")
    return role


def user_id(role):
    return "dm" if role == "admin" else "table"


def rule(path):
    return RULES.get(path.split("/", 1)[0], ("admin", "admin"))


def may_read(role, path):
    return RANK[role] >= RANK[rule(path)[0]]


def may_write(role, path):
    parts = path.split("/")
    if parts[0] == "citypins" and len(parts) == 2 and parts[1] == user_id(role) and RANK[role] >= RANK["interact"]:
        return True
    return RANK[role] >= RANK[rule(path)[1]]


def clean_path(path):
    path = (path or "").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+){0,3}", path):
        raise HTTPException(status_code=400, detail="bad document path")
    return path


# ----------------------------------------------------------------------------------------------- the document store


class Store:
    def __init__(self):
        self.docs, self.rev, self.listeners = {}, {}, set()

    @property
    def file(self):
        return CFG["root"] / "db.json"

    def load(self):
        try:
            raw = json.loads(self.file.read_text(encoding="utf-8"))
            self.docs, self.rev = raw.get("docs", {}), raw.get("rev", {})
        except (OSError, ValueError):
            self.docs, self.rev = {}, {}

    def save(self):
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"docs": self.docs, "rev": self.rev}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.file)

    def get(self, path):
        return path in self.docs, self.docs.get(path), self.rev.get(path, 0)

    def set(self, path, data):
        self.docs[path] = data
        self.rev[path] = self.rev.get(path, 0) + 1
        self.save()
        self.emit(path)
        return self.rev[path]

    def delete(self, path):
        existed = self.docs.pop(path, None) is not None
        if existed:
            self.rev[path] = self.rev.get(path, 0) + 1
            self.save()
            self.emit(path)
        return existed

    def col(self, name):
        prefix = name.strip("/") + "/"
        return [{"id": p[len(prefix):], "data": d} for p, d in sorted(self.docs.items()) if p.startswith(prefix) and "/" not in p[len(prefix):]]

    def emit(self, path):
        exists, data, rev = self.get(path)
        msg = {"path": path, "exists": exists, "data": data, "rev": rev}
        for role, q in list(self.listeners):
            if may_read(role, path):
                q.put_nowait(msg)


STORE = Store()


# ----------------------------------------------------------------------------------------------- assets


def image_size(path):
    """(width, height) of a PNG, JPEG or GIF without any imaging library, or (None, None)."""
    try:
        with open(path, "rb") as f:
            head = f.read(26)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:6] in (b"GIF87a", b"GIF89a"):
                return struct.unpack("<HH", head[6:10])
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        break
                    if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    size = struct.unpack(">H", f.read(2))[0]
                    f.seek(size - 2, 1)
    except (OSError, struct.error):
        pass
    return None, None


class Assets:
    def __init__(self):
        self.items = {}

    @property
    def index(self):
        return CFG["root"] / "assets.json"

    @property
    def folder(self):
        return CFG["root"] / "assets"

    def load(self):
        try:
            self.items = json.loads(self.index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = {}

    def save(self):
        self.index.write_text(json.dumps(self.items, indent=1, ensure_ascii=False), encoding="utf-8")

    def add_bytes(self, name, data, mime=None):
        self.folder.mkdir(parents=True, exist_ok=True)
        aid = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")
        ext = (Path(name).suffix or mimetypes.guess_extension(mime or "") or "")[:8]
        (self.folder / f"{aid}{ext}").write_bytes(data)
        self.items[aid] = {"name": name, "file": f"assets/{aid}{ext}", "mime": mime or mimetypes.guess_type(name)[0] or "application/octet-stream"}
        self.save()
        return aid

    def add_path(self, src):
        """Register a file that already lives in the repo (the campaign's sources/, or the website's images for this campaign) without copying it;
        it is stored relative to the repo root, so the same map data works on any machine that has the repo."""
        p = Path(src)
        repo = CFG["repo"].resolve()
        p = (p if p.is_absolute() else repo / p).resolve()
        allowed = [CFG["camp"].resolve(), (repo / "website" / CFG["camp"].name).resolve()]
        if not p.is_file() or not any(a in p.parents for a in allowed):
            raise HTTPException(status_code=400, detail=f"the file must be inside {allowed[0]} or {allowed[1]}")
        rel = p.relative_to(repo).as_posix()
        for aid, it in self.items.items():
            if it.get("rel") == rel or it.get("abs") == str(p):
                return aid
        aid = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")
        self.items[aid] = {"name": p.name, "rel": rel, "mime": mimetypes.guess_type(p.name)[0] or "application/octet-stream"}
        self.save()
        return aid

    def file_of(self, aid):
        it = self.items.get(aid)
        if not it:
            return None, None
        p = Path(it["abs"]) if it.get("abs") else CFG["repo"] / it["rel"] if it.get("rel") else CFG["root"] / it["file"]
        return (p, it.get("mime")) if p.is_file() else (None, None)


ASSETS = Assets()


# ----------------------------------------------------------------------------------------------- routes


@router.get("/map")
async def map_no_slash(request: Request):
    return RedirectResponse(url="map/" + (("?" + request.url.query) if request.url.query else ""), status_code=307)


@router.get("/map/")
async def map_page(k: str = "", t: str = ""):
    role = need_role(k, t)
    try:
        html = CFG["page"].read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=500, detail="the map page is missing (.claude/skills/dm-battlemap/combined.html)")
    html = html.replace("/_blob/", "_blob/")  # relative, so the page also works under /<campaign>/chat/map/
    boot = ('<script>window.__MAP=' + json.dumps({"role": role, "key": CFG["dm"] if role == "admin" else CFG["table"]}) + ';</script>'
            '<script src="_shim.js"></script>')
    # combined.html is a page body (it has no document wrapper of its own): wrap it, with the runtime stand-in first
    html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' + boot + '</head><body>'
            + html + '</body></html>')
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/map/_shim.js")
async def map_shim():
    return FileResponse(CFG["here"] / "static" / "map-shim.js", media_type="text/javascript", headers={"Cache-Control": "no-store"})


@router.get("/map/_doc")
async def map_get_doc(path: str, k: str = "", t: str = "", x_dm_key: str = Header(default=""), x_table_key: str = Header(default="")):
    role = need_role(k, t, x_dm_key, x_table_key)
    path = clean_path(path)
    if path == "places":                                            # virtual, read-only: the places list travels over the same route as the documents, so the web proxy needs no extra rule
        return {"path": path, "exists": True, "data": places_data(role == "admin"), "rev": 0}
    if not may_read(role, path):
        raise HTTPException(status_code=403, detail=f"this key cannot read {path}")
    exists, data, rev = STORE.get(path)
    return {"path": path, "exists": exists, "data": data, "rev": rev}


@router.put("/map/_doc")
async def map_put_doc(path: str, request: Request, k: str = "", t: str = "", x_dm_key: str = Header(default=""), x_table_key: str = Header(default="")):
    role = need_role(k, t, x_dm_key, x_table_key)
    path = clean_path(path)
    if not may_write(role, path):
        raise HTTPException(status_code=403, detail=f"this key cannot write {path}")
    raw = await request.body()
    if len(raw) > MAX_DOC:
        raise HTTPException(status_code=413, detail="document too large")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="body must be JSON")
    if "data" not in body:
        raise HTTPException(status_code=400, detail='body must be {"data": ...}')
    return {"ok": True, "path": path, "rev": STORE.set(path, body["data"])}


@router.delete("/map/_doc")
async def map_delete_doc(path: str, k: str = "", t: str = "", x_dm_key: str = Header(default=""), x_table_key: str = Header(default="")):
    role = need_role(k, t, x_dm_key, x_table_key)
    path = clean_path(path)
    if not may_write(role, path):
        raise HTTPException(status_code=403, detail=f"this key cannot delete {path}")
    return {"ok": True, "deleted": STORE.delete(path)}


@router.get("/map/_col")
async def map_get_col(name: str, k: str = "", t: str = "", x_dm_key: str = Header(default=""), x_table_key: str = Header(default="")):
    role = need_role(k, t, x_dm_key, x_table_key)
    name = clean_path(name)
    if not may_read(role, name):
        raise HTTPException(status_code=403, detail=f"this key cannot read {name}")
    return {"name": name, "docs": STORE.col(name)}


@router.get("/map/_docs")
async def map_list_docs(k: str = "", x_dm_key: str = Header(default="")):
    role = need_role(k=k, x_dm_key=x_dm_key)
    return [{"path": p, "rev": STORE.rev.get(p, 0), "bytes": len(json.dumps(d))} for p, d in sorted(STORE.docs.items()) if may_read(role, p)]


# ----------------------------------------------------------------------------------------------- known places (for the pin editor)
def _title_of(md):
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return md.stem.replace("-", " ").title()


def _norm(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower().replace("the ", "", 1) if name.lower().startswith("the ") else name.lower())


def places_data(admin):
    """What the pin editor offers: the places the party knows (website world.json + world-public.json, the same data as the Places section
    of the website, so nothing the players have not been told) and, for the DM only, the campaign's other locations with no card yet."""
    camp = CFG["camp"]
    site = CFG["repo"] / "website" / camp.name

    def load(name):
        try:
            return json.loads((site / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    cards = next((sec.get("cards", []) for sec in load("world.json").get("sections", []) if sec.get("id") == "section-places"), [])
    public = {p["id"]: p for p in load("world-public.json").get("places", [])}
    aliases = load("world-aliases.json")
    known, slugs, names = [], set(), set()
    for card in cards:
        slug = card.get("public") or card.get("id")
        rec = public.get(slug) or {}
        paras = list(rec.get("description") or card.get("body") or ([rec["what"]] if rec.get("what") else []))
        if rec.get("detail"):
            paras.append(str(rec["detail"]).rstrip(".") + ".")
        img = ""
        if card.get("place"):                                       # the location's picture on the website: registered by path (no copy) so /map/_blob/<id> can serve it
            try:
                img = ASSETS.add_path(site / card["place"])
            except HTTPException:
                img = ""
        known.append({"slug": slug, "name": card.get("name") or rec.get("name") or slug, "desc": "\n\n".join(str(x) for x in paras), "img": img})
        slugs.update({slug, card.get("id")})
        names.add(_norm(known[-1]["name"]))
    slugs.update(aliases.keys())
    slugs.update(aliases.values())
    known.sort(key=lambda x: x["name"].lower())
    out = {"known": known}
    if admin:
        unknown, seen = [], set()
        for folder in ("info/locations", "party/locations"):
            for md in sorted((camp / folder).glob("*.md")):
                if md.stem in slugs or md.stem in seen or md.stem.endswith("-map") or md.stem == "waterdeep-city":
                    continue
                name = _title_of(md)
                if _norm(name) in names:
                    continue
                seen.add(md.stem)
                unknown.append({"slug": md.stem, "name": name})
        out["unknown"] = sorted(unknown, key=lambda x: x["name"].lower())
    return out


@router.get("/map/_places")
async def map_places(k: str = "", t: str = "", x_dm_key: str = Header(default=""), x_table_key: str = Header(default="")):
    role = need_role(k, t, x_dm_key, x_table_key)
    return places_data(role == "admin")


@router.get("/map/_events")
async def map_events(k: str = "", t: str = ""):
    role = need_role(k, t)
    q = asyncio.Queue()
    entry = (role, q)
    STORE.listeners.add(entry)

    async def gen():
        yield "event: ready\ndata: {}\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), 15)
                    yield "event: doc\ndata: " + json.dumps(msg, ensure_ascii=False) + "\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            STORE.listeners.discard(entry)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/map/_blob/{aid}")
async def map_blob(aid: str):
    # open like the audio route: an <image href> cannot carry a key, and ids are unguessable (the DM-only map's id is never in a document the tablet can read)
    p, mime = ASSETS.file_of(aid)
    if not p or not re.fullmatch(r"[A-Za-z0-9]+", aid):
        raise HTTPException(status_code=404)
    return FileResponse(p, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})


@router.post("/map/_asset")
async def map_upload(file: UploadFile = File(...), k: str = "", x_dm_key: str = Header(default="")):
    need = need_role(k=k, x_dm_key=x_dm_key)
    if need != "admin":
        raise HTTPException(status_code=403, detail="only the DM can upload map images")
    data = await file.read()
    if len(data) > 25_000_000:
        raise HTTPException(status_code=413, detail="image too large (25 MB)")
    aid = ASSETS.add_bytes(file.filename or "map", data, file.content_type)
    p, _ = ASSETS.file_of(aid)
    w, h = image_size(p)
    return {"id": aid, "name": file.filename, "width": w, "height": h}


@router.post("/map/_asset_path")
async def map_register(body: dict, k: str = "", x_dm_key: str = Header(default="")):
    if need_role(k=k, x_dm_key=x_dm_key) != "admin":
        raise HTTPException(status_code=403, detail="only the DM can register map images")
    aid = ASSETS.add_path(body.get("path") or "")
    p, _ = ASSETS.file_of(aid)
    w, h = image_size(p)
    return {"id": aid, "name": p.name, "width": w, "height": h}


@router.get("/map/_assets")
async def map_list_assets(k: str = "", x_dm_key: str = Header(default="")):
    need_role(k=k, x_dm_key=x_dm_key)
    out = []
    for aid, it in ASSETS.items.items():
        p, _ = ASSETS.file_of(aid)
        w, h = image_size(p) if p else (None, None)
        out.append({"id": aid, "name": it["name"], "width": w, "height": h, "present": bool(p)})
    return out
