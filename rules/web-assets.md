# Web assets: JS and CSS versions

Browsers cache `website/js/*.js` and `website/style/*.css`. A page that loads a stale copy breaks silently (cards render empty, panels missing).

- Every `<script src>` and `<link href>` for those files carries `?v=<content hash>`.
- After changing any file in `website/js/`, `website/style/` or `.claude/skills/dm-setup/templates/js|style/`, run `python .claude/scripts/bump_asset_versions.py` (a `PostToolUse` hook does this automatically for Edit/Write; changes made through Bash `sed`, an editor or `git checkout` need a manual run). `--check` lists stale tags.
- New HTML written by a generator must take the version from `bump_asset_versions.version(name)` instead of hard-coding it (`story_to_html.py` already does).
- `dm-setup` and `dm-update` copy the template js/css into `website/`; run the script afterwards.
