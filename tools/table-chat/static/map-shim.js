/* A local stand-in for the page runtime the map page was written for (window.claude.use("db" | "user" | "assets")).
   Documents and collections live on the table chat server (map_service.py) and arrive as server-sent events, so the page's own
   onSnapshot code works unchanged. The page that serves this file sets window.__MAP = {role: "admin" | "interact", key: "..."}. */
(function () {
  var cfg = window.__MAP || {};
  var role = cfg.role || "interact";
  var uid = role === "admin" ? "dm" : "table";
  var base = location.pathname.replace(/[^\/]*$/, "");              // the folder the page was loaded from, ending in /
  var qk = (role === "admin" ? "k=" : "t=") + encodeURIComponent(cfg.key || "");
  function url(name, extra) { return base + name + "?" + qk + (extra ? "&" + extra : ""); }
  function clone(x) { return x === undefined || x === null ? x : JSON.parse(JSON.stringify(x)); }
  function fail(r) { return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.detail || ("HTTP " + r.status)); }); }

  var docWatch = {};    // path -> [callbacks]
  var colWatch = {};    // collection name -> [callbacks]
  var stream = null;

  function docSnap(path, exists, data) {
    return { id: path.split("/").pop(), exists: !!exists, data: function () { return exists ? clone(data) : undefined; },
             metadata: { hasPendingWrites: false, fromCache: false } };
  }
  function colSnap(docs) {
    var list = docs.map(function (d) { return { id: d.id, exists: true, data: function () { return clone(d.data); }, metadata: { hasPendingWrites: false } }; });
    return { docs: list, size: list.length, empty: !list.length, forEach: function (fn) { list.forEach(fn); } };
  }
  function fetchDoc(path) {
    return fetch(url("_doc", "path=" + encodeURIComponent(path))).then(function (r) { return r.ok ? r.json() : fail(r); });
  }
  function fetchCol(name) {
    return fetch(url("_col", "name=" + encodeURIComponent(name))).then(function (r) { return r.ok ? r.json() : fail(r); });
  }
  function pushDoc(path, exists, data) { (docWatch[path] || []).slice().forEach(function (w) { try { w.next(docSnap(path, exists, data)); } catch (e) { console.error(e); } }); }
  function pushCol(name) {
    var ws = colWatch[name] || [];
    if (!ws.length) return;
    fetchCol(name).then(function (r) { ws.slice().forEach(function (w) { try { w.next(colSnap(r.docs)); } catch (e) { console.error(e); } }); }, function (e) { ws.forEach(function (w) { if (w.err) w.err(e); }); });
  }
  function refetchAll() {
    Object.keys(docWatch).forEach(function (p) { fetchDoc(p).then(function (r) { pushDoc(p, r.exists, r.data); }, function () {}); });
    Object.keys(colWatch).forEach(pushCol);
  }
  function ensureStream() {
    if (stream) return;
    stream = new EventSource(url("_events"));
    stream.addEventListener("ready", refetchAll);                   // also after a reconnect, so nothing is missed
    stream.addEventListener("doc", function (e) {
      var m = JSON.parse(e.data);
      if (docWatch[m.path]) pushDoc(m.path, m.exists, m.data);
      Object.keys(colWatch).forEach(function (name) { if (m.path.indexOf(name + "/") === 0) pushCol(name); });
    });
  }
  function watch(table, key, next, err, first) {
    (table[key] = table[key] || []).push({ next: next, err: err });
    ensureStream();
    first();
    return function () { table[key] = (table[key] || []).filter(function (w) { return w.next !== next; }); };
  }

  function docRef(path) {
    return {
      id: path.split("/").pop(), path: path,
      get: function () { return fetchDoc(path).then(function (r) { return docSnap(path, r.exists, r.data); }); },
      set: function (data) {
        return fetch(url("_doc", "path=" + encodeURIComponent(path)), { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ data: data }) })
          .then(function (r) { return r.ok ? undefined : fail(r); });
      },
      update: function (patch) {
        return this.get().then(function (s) { var d = s.exists ? s.data() : {}; Object.keys(patch).forEach(function (k) { d[k] = patch[k]; }); return docRef(path).set(d); });
      },
      delete: function () { return fetch(url("_doc", "path=" + encodeURIComponent(path)), { method: "DELETE" }).then(function (r) { return r.ok ? undefined : fail(r); }); },
      onSnapshot: function (next, err) {
        var error = typeof err === "function" ? err : null;
        return watch(docWatch, path, next, error, function () {
          fetchDoc(path).then(function (r) { next(docSnap(path, r.exists, r.data)); }, function (e) { if (error) error(e); });
        });
      }
    };
  }
  var db = {
    doc: docRef,
    collection: function (name) {
      return {
        doc: function (id) { return docRef(name + "/" + id); },
        get: function () { return fetchCol(name).then(function (r) { return colSnap(r.docs); }); },
        onSnapshot: function (next, err) {
          var error = typeof err === "function" ? err : null;
          return watch(colWatch, name, next, error, function () {
            fetchCol(name).then(function (r) { next(colSnap(r.docs)); }, function (e) { if (error) error(e); });
          });
        }
      };
    }
  };
  var user = {
    canEdit: function () { return Promise.resolve(role === "admin"); },
    can: function (perm) { return Promise.resolve(role === "admin" ? true : /^data\.(read|write)$/.test(perm || "")); },
    id: function () { return Promise.resolve(uid); },
    name: function () { return Promise.resolve(role === "admin" ? "DM" : "Table"); }
  };
  var assets = {
    url: function (id) { return "_blob/" + id; },
    upload: function (file) {
      var fd = new FormData();
      fd.append("file", file, file.name || "map");
      return fetch(url("_asset"), { method: "POST", body: fd }).then(function (r) { return r.ok ? r.json() : fail(r); }).then(function (j) { j.url = "_blob/" + j.id; return j; });
    }
  };

  var places = { get: function () { return fetch(url("_doc", "path=places")).then(function (r) { return r.ok ? r.json() : fail(r); }).then(function (j) { return j.data; }); } };   // known places for the pin editor
  window.claude = window.claude || {};
  window.claude.use = function (name) {
    var cap = { db: db, user: user, assets: assets, places: places }[name];
    return cap ? Promise.resolve(cap) : Promise.reject(new Error("capability not available: " + name));
  };
})();
