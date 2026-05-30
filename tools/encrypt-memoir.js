#!/usr/bin/env node
/**
 * encrypt-memoir.js — encrypts a plaintext memoir JSON for use with memoir.js
 *
 * Usage (run from anywhere):
 *   node tools/encrypt-memoir.js <plaintext-json> <slot>
 *
 * Example:
 *   node tools/encrypt-memoir.js campaigns/waterdeep-dragon-heist/party/session-5/session-5-caelith.json caelith
 *
 * Slot → player mapping is read from website/<campaign>/assets/memoir-config.json.
 * Passwords are read from the root .env file. Required keys: PASSWORD_<PLAYER>
 * (e.g. PASSWORD_LOTTE, PASSWORD_BENV) — one entry per player including the DM.
 *
 * Output: website/<campaign>/assets/memoirs/<basename>  (encrypted, ready to serve)
 *
 * Encrypted file format:
 *   { v, keys: { <slot>: wrappedKey, dm: wrappedKey }, iv, data }
 *
 * Both the character key and the DM key can independently decrypt the content key.
 */

const { webcrypto } = require('crypto');
const crypto = webcrypto;
const fs   = require('fs');
const path = require('path');

// ── Load a .env file into an object ──────────────────────────────────────────

function loadEnvFile(filePath) {
  const env = {};
  if (!fs.existsSync(filePath)) return env;
  fs.readFileSync(filePath, 'utf8').split('\n').forEach(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return;
    const eq = trimmed.indexOf('=');
    if (eq === -1) return;
    env[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  });
  return env;
}

// ── Find repo root (contains tools/ directory) ────────────────────────────────

function findRepoRoot(startDir) {
  let dir = path.resolve(startDir);
  const root = path.parse(dir).root;
  while (dir !== root) {
    if (fs.existsSync(path.join(dir, '.claude', 'tools', 'encrypt-memoir.js'))) return dir;
    dir = path.dirname(dir);
  }
  return null;
}

// ── Args ──────────────────────────────────────────────────────────────────────

const [,, inputFile, slot] = process.argv;

if (!inputFile || !slot) {
  console.error('Usage: node tools/encrypt-memoir.js <plaintext-json> <slot>');
  console.error('Example: node tools/encrypt-memoir.js campaigns/waterdeep-dragon-heist/party/session-5/session-5-caelith.json caelith');
  process.exit(1);
}

const inputAbs = path.resolve(inputFile);
if (!fs.existsSync(inputAbs)) {
  console.error(`Error: input file not found: ${inputAbs}`);
  process.exit(1);
}

// ── Resolve campaign slug from input path ─────────────────────────────────────

const inputParts = inputAbs.split(path.sep);
const campaignsIdx = inputParts.lastIndexOf('campaigns');
if (campaignsIdx === -1) {
  console.error('Error: input path must be inside a campaigns/<slug>/ directory');
  process.exit(1);
}
const campaignSlug = inputParts[campaignsIdx + 1];

// ── Find repo root ────────────────────────────────────────────────────────────

const repoRoot = findRepoRoot(path.dirname(inputAbs));
if (!repoRoot) {
  console.error('Error: could not find repo root (looking for tools/encrypt-memoir.js)');
  process.exit(1);
}

// ── Load memoir-config.json for slot → player mapping ────────────────────────

const memoirConfigPath = path.join(repoRoot, 'website', campaignSlug, 'assets', 'memoir-config.json');
if (!fs.existsSync(memoirConfigPath)) {
  console.error(`Error: memoir-config.json not found at ${memoirConfigPath}`);
  process.exit(1);
}
const memoirConfig = JSON.parse(fs.readFileSync(memoirConfigPath, 'utf8'));

const charEntry = memoirConfig.characters && memoirConfig.characters[slot.toLowerCase()];
if (!charEntry || !charEntry.player) {
  console.error(`Error: slot "${slot}" not found in ${memoirConfigPath}`);
  console.error('Add it to the "characters" section and re-run.');
  process.exit(1);
}
const charPlayer = charEntry.player;
const dmPlayer   = memoirConfig.dm;
if (!dmPlayer) {
  console.error(`Error: "dm" field not set in ${memoirConfigPath}`);
  process.exit(1);
}

// ── Load .env for passwords ───────────────────────────────────────────────────

const rootEnvPath = path.join(repoRoot, '.env');
if (!fs.existsSync(rootEnvPath)) {
  console.error(`Error: root .env not found at ${rootEnvPath}`);
  console.error('Create it with PASSWORD_<PLAYER>=... entries. See .env.example.');
  process.exit(1);
}
const env = loadEnvFile(rootEnvPath);

const dmPassword   = env[`PASSWORD_${dmPlayer.toUpperCase()}`];
const charPassword = env[`PASSWORD_${charPlayer.toUpperCase()}`];

if (!dmPassword) {
  console.error(`Error: PASSWORD_${dmPlayer.toUpperCase()} not set in .env (DM player password)`);
  process.exit(1);
}
if (!charPassword) {
  console.error(`Error: PASSWORD_${charPlayer.toUpperCase()} not set in .env (player for ${slot})`);
  process.exit(1);
}

// ── Crypto ────────────────────────────────────────────────────────────────────

const enc = new TextEncoder();

function bytesToB64(bytes) {
  return Buffer.from(bytes).toString('base64');
}

async function deriveKwKey(password, keySlot) {
  const base = await crypto.subtle.importKey(
    'raw', enc.encode(password.toLowerCase().trim()),
    'PBKDF2', false, ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: enc.encode('memoir-salt-' + keySlot), iterations: 100000, hash: 'SHA-256' },
    base,
    { name: 'AES-KW', length: 256 },
    false,
    ['wrapKey']
  );
}

async function main() {
  const entries = JSON.parse(fs.readFileSync(inputAbs, 'utf8'));
  const filtered = entries
    .map(e => ({
      anchor: e.anchor,
      blocks: (e.blocks || []).filter(b => b.type === 'private'),
    }))
    .filter(e => e.blocks.length > 0);
  const plaintext = JSON.stringify(filtered, null, 2);

  // Generate a random content key (AES-GCM)
  const contentKey = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 }, true, ['encrypt']
  );

  // Encrypt the plaintext data
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    contentKey,
    enc.encode(plaintext)
  );

  // Wrap the content key with the character's derived key
  const charKwKey = await deriveKwKey(charPassword, slot);
  const wrappedForChar = await crypto.subtle.wrapKey('raw', contentKey, charKwKey, 'AES-KW');

  // Wrap the content key with the DM's derived key (slot: 'dm')
  const dmKwKey = await deriveKwKey(dmPassword, 'dm');
  const wrappedForDm = await crypto.subtle.wrapKey('raw', contentKey, dmKwKey, 'AES-KW');

  const output = {
    v: 1,
    keys: {
      [slot]: bytesToB64(new Uint8Array(wrappedForChar)),
      dm:     bytesToB64(new Uint8Array(wrappedForDm)),
    },
    iv:   bytesToB64(iv),
    data: bytesToB64(new Uint8Array(encrypted)),
  };

  // Write to website/<slug>/assets/memoirs/<basename> (or <basename-private> for private-only)
  const outputDir = path.join(repoRoot, 'website', campaignSlug, 'assets', 'memoirs');
  fs.mkdirSync(outputDir, { recursive: true });
  const outputFile = path.join(outputDir, path.basename(inputAbs, '.json') + '-private.json');

  fs.writeFileSync(outputFile, JSON.stringify(output, null, 2));
  console.log(`✓  ${outputFile}`);
}

main().catch(err => { console.error(err); process.exit(1); });
