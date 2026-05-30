const COOKIE_KEY = "memoir_key_";
const COOKIE_DAYS = 30;

// ── Global config ─────────────────────────────────────────────────────────────
// Loaded async from ../assets/config.json (one level up, shared across all campaigns).
// Format: { "players": { "lotte": { "hash": "..." }, ... }, "ttsBackend": "moss" }
let globalConfig = null;

async function loadGlobalConfig() {
  if (globalConfig) return globalConfig;
  try {
    const resp = await fetch("../assets/config.json", { cache: "no-cache" });
    if (resp.ok) globalConfig = await resp.json();
  } catch {}
  return globalConfig || {};
}

function getPlayers() {
  return (globalConfig && globalConfig.players) || {};
}

// ── Campaign config ───────────────────────────────────────────────────────────
// Loaded async from assets/memoir-config.json (per-campaign).
// Format: { "dm": "lotte", "characters": { "caelith": { player, name, color, portrait }, ... } }
let campaignConfig = null;

async function loadCampaignConfig() {
  if (campaignConfig) return campaignConfig;
  try {
    const resp = await fetch("assets/memoir-config.json", { cache: "no-cache" });
    if (resp.ok) campaignConfig = await resp.json();
  } catch {}
  return campaignConfig || {};
}

function getCharacters() {
  return (campaignConfig && campaignConfig.characters) || {};
}

// ── Cookie helpers ────────────────────────────────────────────────────────────

function setCookie(name, value, days) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Strict`;
}

function getCookie(name) {
  return document.cookie.split("; ").reduce((acc, part) => {
    const [k, ...rest] = part.split("=");
    return k === name ? rest.join("=") : acc;
  }, null);
}

function deleteCookie(name) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; SameSite=Strict`;
}

// ── Crypto helpers ────────────────────────────────────────────────────────────

const enc = new TextEncoder();
const dec = new TextDecoder();

function b64ToBytes(b64) {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

function bytesToB64(bytes) {
  return btoa(String.fromCharCode(...bytes));
}

async function sha256(str) {
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(str));
  return [...new Uint8Array(buf)]
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
}

async function deriveKey(password, salt) {
  const base = await crypto.subtle.importKey(
    "raw",
    enc.encode(password.toLowerCase().trim()),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: enc.encode("memoir-salt-" + salt),
      iterations: 100000,
      hash: "SHA-256",
    },
    base,
    { name: "AES-KW", length: 256 },
    true,
    ["wrapKey", "unwrapKey"],
  );
}

async function keyToB64(key) {
  const raw = await crypto.subtle.exportKey("raw", key);
  return bytesToB64(new Uint8Array(raw));
}

async function b64ToKey(b64, usage) {
  const raw = b64ToBytes(b64);
  return crypto.subtle.importKey("raw", raw, { name: "AES-KW" }, false, usage);
}

async function tryUnwrap(wrappedB64, kwKey) {
  try {
    return await crypto.subtle.unwrapKey(
      "raw",
      b64ToBytes(wrappedB64),
      kwKey,
      "AES-KW",
      { name: "AES-GCM", length: 256 },
      false,
      ["decrypt"],
    );
  } catch {
    return null;
  }
}

async function decryptData(ivB64, dataB64, contentKey) {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: b64ToBytes(ivB64) },
    contentKey,
    b64ToBytes(dataB64),
  );
  return JSON.parse(dec.decode(plaintext));
}

// ── Audio button helper ───────────────────────────────────────────────────────

function makeAudioButton(src, label) {
  const btn = document.createElement("button");
  btn.className = "audio-play-btn memoir-audio-btn";
  btn.title = `Play ${label}`;
  btn.dataset.src = src;
  btn.dataset.label = label;
  btn.style.display = "none";
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12">
    <path class="icon-play"  d="M8 5v14l11-7z"/>
    <path class="icon-pause" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" style="display:none"/>
  </svg>`;

  const showIfEnabled = () => {
    if (window.CAMPAIGN_AUDIO_ENABLED === true) {
      btn.style.display = "";
      btn.addEventListener("click", () => {
        if (window.audioPlay) window.audioPlay(btn);
      });
    } else if (window.CAMPAIGN_AUDIO_ENABLED === false) {
      btn.remove();
    } else {
      setTimeout(showIfEnabled, 100);
    }
  };
  setTimeout(showIfEnabled, 100);
  return btn;
}

// ── Public memoir loading (no key required) ───────────────────────────────────

async function loadPublicMemoirs() {
  const session = location.pathname.split("/").pop().replace(".html", "");
  const chars = getCharacters();
  for (const [slot, char] of Object.entries(chars)) {
    let resp;
    try {
      resp = await fetch(`assets/memoirs/${session}-${slot}-public.json`, { cache: "no-cache" });
    } catch { continue; }
    if (!resp.ok) continue;

    const entries = await resp.json();
    for (const entry of entries) {
      const anchorEl = document.getElementById(entry.anchor);
      if (!anchorEl) continue;
      // Only p blocks in the public file
      const publicBlocks = (entry.blocks || []).filter(b => b.type === "p");
      if (!publicBlocks.length) continue;
      anchorEl.appendChild(buildPublicCallout(publicBlocks, char, slot, entry.anchor, session));
    }
  }
}

function buildPublicCallout(blocks, char, slot, anchor, session) {
  const audioSrc = `audio/${session}/memoir-${slot}-${anchor}-public.mp3`;
  const label = `${char.name} — memoir`;

  const el = document.createElement("div");
  el.className = "memoir-callout memoir-callout-public";
  el.dataset.anchor = anchor;
  el.dataset.slot = slot;
  el.style.setProperty("--char-color", char.color);

  const nameDiv = document.createElement("div");
  nameDiv.className = "memoir-callout-name";
  nameDiv.textContent = char.name;
  nameDiv.appendChild(makeAudioButton(audioSrc, label));

  const bodyDiv = document.createElement("div");
  bodyDiv.className = "memoir-callout-body";
  bodyDiv.appendChild(nameDiv);
  blocks.forEach(b => {
    const p = document.createElement("p");
    p.textContent = b.text;
    bodyDiv.appendChild(p);
  });

  const img = document.createElement("img");
  img.className = "memoir-callout-portrait";
  img.src = char.portrait;
  img.alt = char.name;

  el.appendChild(img);
  el.appendChild(bodyDiv);
  return el;
}

// ── Private memoir loading (requires key) ─────────────────────────────────────

async function loadPrivateMemoir(session, slot, kwKey, isDmKey = false) {
  let resp;
  try {
    resp = await fetch(`assets/memoirs/${session}-${slot}-private.json`, { cache: "no-cache" });
  } catch { return; }
  if (!resp.ok) return;

  const file = await resp.json();
  if (file.v !== 1) return;

  const wrappedKey = isDmKey ? file.keys["dm"] : file.keys[slot];
  if (!wrappedKey) return;

  const contentKey = await tryUnwrap(wrappedKey, kwKey);
  if (!contentKey) return;

  const entries = await decryptData(file.iv, file.data, contentKey);
  renderPrivateEntries(entries, slot, session);
}

function renderPrivateEntries(entries, slot, session) {
  const char = getCharacters()[slot];
  if (!char) return;

  for (const entry of entries) {
    const anchorEl = document.getElementById(entry.anchor);
    if (!anchorEl) continue;

    const privateBlocks = (entry.blocks || []).filter(b => b.type === "private");
    if (!privateBlocks.length) continue;

    // Find existing public callout for this anchor+slot to append to
    const existing = anchorEl.querySelector(`.memoir-callout[data-slot="${slot}"]`);
    const audioSrc = `audio/${session}/memoir-${slot}-${entry.anchor}-private.mp3`;
    const label = `${char.name} — private memoir`;

    if (existing) {
      // Append private content + audio button to existing public callout
      const body = existing.querySelector(".memoir-callout-body");
      const nameDiv = existing.querySelector(".memoir-callout-name");
      privateBlocks.forEach(b => {
        const p = document.createElement("p");
        p.className = "private-note";
        p.textContent = b.text;
        body.appendChild(p);
      });
      const privateBtn = makeAudioButton(audioSrc, label);
      privateBtn.classList.add("memoir-audio-btn-private");
      nameDiv.appendChild(privateBtn);
    } else {
      // No public callout — build a standalone private callout
      anchorEl.appendChild(buildPrivateCallout(privateBlocks, char, slot, entry.anchor, session, audioSrc, label));
    }
  }
}

function buildPrivateCallout(blocks, char, slot, anchor, session, audioSrc, label) {
  const el = document.createElement("div");
  el.className = "memoir-callout memoir-callout-private";
  el.dataset.anchor = anchor;
  el.dataset.slot = slot;
  el.style.setProperty("--char-color", char.color);

  const nameDiv = document.createElement("div");
  nameDiv.className = "memoir-callout-name";
  nameDiv.textContent = char.name;
  const privateBtn = makeAudioButton(audioSrc, label);
  privateBtn.classList.add("memoir-audio-btn-private");
  nameDiv.appendChild(privateBtn);

  const bodyDiv = document.createElement("div");
  bodyDiv.className = "memoir-callout-body";
  bodyDiv.appendChild(nameDiv);
  blocks.forEach(b => {
    const p = document.createElement("p");
    p.className = "private-note";
    p.textContent = b.text;
    bodyDiv.appendChild(p);
  });

  const img = document.createElement("img");
  img.className = "memoir-callout-portrait";
  img.src = char.portrait;
  img.alt = char.name;

  el.appendChild(img);
  el.appendChild(bodyDiv);
  return el;
}

// ── Logout bar ────────────────────────────────────────────────────────────────

function showLogoutBar(playerIds, isDm) {
  if (document.getElementById("memoir-logout-bar")) return;
  const bar = document.createElement("div");
  bar.id = "memoir-logout-bar";
  const who = isDm ? "DM view" : playerIds.join(", ");
  bar.innerHTML = `<span>Private memoirs unlocked: <strong>${who}</strong></span>
    <button onclick="memoirLogout()">Log out</button>`;
  document.body.appendChild(bar);

  const loginBar = document.getElementById("memoir-login-bar");
  if (loginBar) loginBar.remove();
}

function memoirLogout() {
  if (window.chapterAudioStop) window.chapterAudioStop();
  Object.keys(getCharacters()).forEach((slot) => deleteCookie(COOKIE_KEY + slot));
  Object.keys(getPlayers()).forEach((p) => deleteCookie(COOKIE_KEY + "dm_" + p));
  location.reload();
}

// ── Login bar ─────────────────────────────────────────────────────────────────

function initLoginWidget() {
  const navWidget = document.getElementById("memoir-login-widget");
  if (navWidget) navWidget.style.display = "none";

  if (document.getElementById("memoir-login-bar")) return;
  const bar = document.createElement("div");
  bar.id = "memoir-login-bar";
  bar.innerHTML = `<span>Private memoirs</span>
    <input type="password" id="memoir-pw" placeholder="Password…" autocomplete="current-password">
    <button onclick="memoirLogin()">Unlock</button>
    <span id="memoir-pw-error"></span>`;
  document.body.appendChild(bar);

  const pw = document.getElementById("memoir-pw");
  if (pw)
    pw.addEventListener("keydown", (e) => {
      if (e.key === "Enter") memoirLogin();
    });
}

async function memoirLogin() {
  const config = await loadCampaignConfig();
  const dmPlayer = config.dm || null;

  const pwEl = document.getElementById("memoir-pw");
  const errorEl = document.getElementById("memoir-pw-error");
  const pw = pwEl ? pwEl.value : "";
  if (!pw) {
    if (errorEl) errorEl.textContent = "Enter password.";
    return;
  }

  const hash = await sha256(pw.toLowerCase().trim());

  for (const [playerId, player] of Object.entries(getPlayers())) {
    if (hash !== player.hash) continue;

    const isDm = dmPlayer && playerId === dmPlayer;

    if (isDm) {
      const dmKey = await deriveKey(pw, "dm");
      setCookie(COOKIE_KEY + "dm_" + playerId, await keyToB64(dmKey), COOKIE_DAYS);
      await loadPrivateMemoirsWithKeys({ dm: dmKey }, playerId, true);
      return;
    }

    const playerChars = Object.entries(getCharacters()).filter(
      ([, c]) => c.player === playerId,
    );
    if (playerChars.length === 0) {
      if (errorEl) errorEl.textContent = "No character found for this password.";
      return;
    }

    const keys = {};
    for (const [slot] of playerChars) {
      const key = await deriveKey(pw, slot);
      setCookie(COOKIE_KEY + slot, await keyToB64(key), COOKIE_DAYS);
      keys[slot] = key;
    }
    await loadPrivateMemoirsWithKeys(keys, playerId, false);
    return;
  }

  if (errorEl) errorEl.textContent = "Wrong password.";
  if (pwEl) pwEl.value = "";
}

// ── Load private memoirs with a keys map ──────────────────────────────────────

async function loadPrivateMemoirsWithKeys(keys, playerDisplay, isDm) {
  const session = location.pathname.split("/").pop().replace(".html", "");
  for (const slot of Object.keys(getCharacters())) {
    if (keys[slot]) {
      await loadPrivateMemoir(session, slot, keys[slot], false);
    } else if (keys["dm"]) {
      await loadPrivateMemoir(session, slot, keys["dm"], true);
    }
  }
  showLogoutBar([playerDisplay], isDm);
}

// ── Restore from cookies on page load ────────────────────────────────────────

async function loadUnlockedMemoirs() {
  const config = await loadCampaignConfig();
  const dmPlayer = config.dm || null;

  if (dmPlayer) {
    const dmB64 = getCookie(COOKIE_KEY + "dm_" + dmPlayer);
    if (dmB64) {
      try {
        const dmKey = await b64ToKey(dmB64, ["wrapKey", "unwrapKey"]);
        await loadPrivateMemoirsWithKeys({ dm: dmKey }, dmPlayer, true);
        return;
      } catch {
        deleteCookie(COOKIE_KEY + "dm_" + dmPlayer);
      }
    }
  }

  const keys = {};
  let playerDisplay = null;
  for (const [slot, char] of Object.entries(getCharacters())) {
    const b64 = getCookie(COOKIE_KEY + slot);
    if (b64) {
      try {
        keys[slot] = await b64ToKey(b64, ["wrapKey", "unwrapKey"]);
        playerDisplay = playerDisplay || char.player;
      } catch {
        deleteCookie(COOKIE_KEY + slot);
      }
    }
  }

  if (Object.keys(keys).length === 0) return;
  await loadPrivateMemoirsWithKeys(keys, playerDisplay, false);
}

async function applySpeakerColors() {
  try {
    const resp = await fetch("assets/memoir-config.json", { cache: "no-cache" });
    if (!resp.ok) return;
    const config = await resp.json();
    const colorMap = {};
    for (const char of Object.values(config.characters || {})) {
      if (char.name && char.color) {
        colorMap[char.name.split(" ")[0]] = char.color;
        colorMap[char.name] = char.color;
      }
    }
    document.querySelectorAll(".dialogue[data-speaker]").forEach(el => {
      const color = colorMap[el.dataset.speaker];
      if (color) el.style.setProperty("--speaker-color", color);
    });
  } catch { /* no config — CSS default applies */ }
}

document.addEventListener("DOMContentLoaded", async () => {
  await loadGlobalConfig();
  await loadCampaignConfig();
  initLoginWidget();
  await loadPublicMemoirs();
  await loadUnlockedMemoirs();
  applySpeakerColors();
});
