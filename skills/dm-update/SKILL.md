---
description: Update framework files (CLAUDE.md, .gitignore, JS, CSS) from the .claude templates after pulling fixes from the repo. Never touches campaign content, config, or the root website/index.html.
argument-hint: ""
---

# DM Update

Run this after pulling changes from the `.claude` git repository to apply any fixes or improvements to framework files.

This skill **only updates shared infrastructure files**. It never touches:
- `website/index.html` (campaign listing — user-managed)
- `website/assets/config.json` (player config — user-managed)
- Any campaign folder under `website/[campaign]/`
- Any `campaigns/` files

---

## Step 1 — Check prerequisites

Verify `website/js/` and `website/style/` exist. If not, tell the DM to run `/dm-setup` first.

State the absolute path of `PROJECT_ROOT` — the directory containing `CLAUDE.md`.

---

## Step 2 — Copy updated files

Copy each file from `.claude/skills/dm-setup/templates/` using `Bash(cp ...)`, overwriting whatever is there:

- `templates/CLAUDE.md` → `CLAUDE.md` (project root)
- `templates/.gitignore` → `.gitignore` (project root)
- `templates/js/audio.js` → `website/js/audio.js`
- `templates/js/lightbox.js` → `website/js/lightbox.js`
- `templates/js/memoir.js` → `website/js/memoir.js`
- `templates/js/nav.js` → `website/js/nav.js`
- `templates/js/world.js` → `website/js/world.js`
- `templates/style/story.css` → `website/style/story.css`
- `templates/style/private.css` → `website/style/private.css`

---

## Step 3 — Confirm

Report what was updated:

```
✓ CLAUDE.md
✓ .gitignore
✓ website/js/audio.js
✓ website/js/lightbox.js
✓ website/js/memoir.js
✓ website/js/nav.js
✓ website/js/world.js
✓ website/style/story.css
✓ website/style/private.css

Framework files updated. Campaign content and config unchanged.
```
