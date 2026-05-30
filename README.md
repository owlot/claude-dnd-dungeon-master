# Claude Dungeon Master

A D&D 5e DM assistant built on Claude Code. Handles the mechanical and administrative work of running a campaign — tracking HP, managing combat, voicing NPCs, logging sessions, generating narrative — so the DM can focus on the table.

This is not a chatbot. It's a persistent campaign system that runs inside Claude Code, with sub-agents, slash commands, structured campaign files, and optional audio/website output.

> **Background reading.** I wrote about building this, and what it taught me about where LLMs fail, in a blog series on the Xebia blog: *Building a D&D Dungeon Master out of Claude*. The companion post *How I Actually Build Agents* walks through the architecture in this repo (many small agents, tool scoping, per-agent model selection, deterministic scripts, two permission files, hooks). Links: [xebia.com/blog](https://xebia.com/blog/).

---

## What It Does

### Session management
- Starts and ends sessions with full state persistence
- Recaps last session, shows party status, flags likely encounters
- Updates character files, `state.md`, and session logs automatically at end of session

### Combat
- Runs initiative, tracks HP and conditions turn by turn
- Calculates hits against AC, prompts for damage rolls
- Renders a live Combat Status Block after each change
- Writes a full combat log at end of fight

### NPC conversations
- Voices named NPCs based on their encounter file or character card
- Tracks disposition shifts, information revealed/withheld, commitments made
- Logs every exchange to a dedicated NPC conversation file
- Appends a clean summary to the session conversation log

### Character tracking
- Maintains HP, spell slots, conditions, resources, and gold per character
- Handles short and long rests, level-ups, loot distribution
- Character files persist between sessions

### Rules lookup
- Delegates monster stat blocks, spells, conditions, magic items, and class features to an SRD lookup agent
- Verifies encounter stat blocks before combat starts

### Narrative and website output
- Writes a novel-style session story after each session
- Generates an HTML session page, encrypted per-character memoir files, and updates a world reference page
- Memoir files are password-protected per character

### Audio tools (optional, in `.claude/tools/`)
- Audition and lock voices per character and NPC using Qwen3-TTS or MOSS-TTS
- Generate per-chapter session audio with character-specific voices
- Generate per-anchor memoir audio split into public and private files, unlockable per player

---

## How It Works

The system runs inside **Claude Code** using three layers:

**CLAUDE.md** — The core instruction file. Defines the DM's role, combat flow, NPC voicing rules, narration format, command reference, and which sub-agents handle which tasks.

**`.claude/agents/`** — Twelve specialized sub-agents, each with a defined scope:

| Agent | Responsibility |
|-------|---------------|
| `session-manager` | Start/end session, update all state files |
| `combat-tracker` | Initiative, HP, conditions, combat log |
| `character-tracker` | PC stats between sessions and mid-session |
| `character-creation` | Walk through character creation |
| `conversation-tracker` | Voice NPCs, track disposition, write NPC logs |
| `conversation-log-appender` | Append NPC conversation summaries to session log |
| `encounter-verifier` | Cross-check stat blocks against SRD before combat |
| `indexer` | Parse all source files in `campaigns/[name]/sources/` into structured campaign files |
| `srd-lookup` | Rules lookups without polluting main context |
| `scene-image-generator` | Generate cinematic scene images and wire into session HTML |
| `story-teller` | Write session story draft from logs |
| `website-generator` | Generate HTML, memoirs, encrypted files, world page |

**`.claude/skills/`** — Slash commands the DM uses at the table:

| Command | What it does |
|---------|-------------|
| `/dm-start-session [campaign]` | Briefing, party status, session prep |
| `/dm-end-session` | Save everything, write story, generate website |
| `/dm-index-campaign [name]` | Parse all files in `campaigns/[name]/sources/` into campaign structure |
| `/dm-load-encounter [name]` | Verify and display encounter, prepare for combat |
| `/dm-create-characters [campaign]` | Walk through character creation for all players |
| `/dm-add-character [name] for [campaign]` | Add a single character to an existing campaign |
| `/dm-show-character [name]` | Display full current character sheet |
| `/dm-rest [short\|long] [campaign]` | Handle a rest — HP, slots, resources |
| `/dm-loot [campaign]` | Distribute loot, update character files |
| `/dm-level-up [character] [campaign]` | Walk through a level-up |
| `/dm-checkpoint [campaign]` | Snapshot all state to `.checkpoints/` |
| `/dm-checkpoint-log [campaign]` | Flush conversation log mid-session |
| `/dm-combat-log [campaign] [slug]` | Retroactively write a combat log from conversation history |
| `/dm-conversation-log [campaign] [npc]` | Retroactively write an NPC conversation log from conversation history |
| `/dm-generate-npc [role]` | Generate a named NPC on the fly |
| `/dm-generate-campaign [name]` | Walk through new campaign generation |
| `/dm-generate-audio [campaign] [session]` | Generate scene and memoir MP3s for a session |
| `/dm-generate-scene-images [campaign] [session]` | Pick and generate scene images, wire into session HTML |
| `/dm-undo [campaign]` | Restore from last checkpoint |
| `/dm-recover-session-log [campaign]` | Rebuild log from raw transcript (recovery only) |

---

## Campaign File Structure

```
campaigns/[name]/
  sources/              — raw source files (PDFs, markdown) placed here by the DM
  info/
    encounters/         — one file per encounter
    npcs/               — one file per NPC (character, voice, stats, background)
    locations/          — one file per location
    introductions/      — character introduction files for voice auditioning
  party/
    state.md            — current situation, session #, location, quests, threads
    session-log.md      — one entry per session
    relationships.md    — NPC relationship tracker
    combat_state.json   — live combat state (written during combat)
    voice-overrides.json — TTS voice slot assignments for minor characters
    phonetic-substitutions.json — TTS pronunciation overrides
    characters/         — one file per PC
    session-N/
      session-N-story.md
      session-N-conversation.md
      session-N-combat-[slug].md
      session-N-npc-[N]-[slug].md
      session-N-[character].json  — memoir JSON files (public and private blocks)

website/
  index.html            — campaign list (not overwritten by /dm-update)
  js/                   — shared JS files (deployed by /dm-setup, updated by /dm-update)
  style/                — shared CSS files (deployed by /dm-setup, updated by /dm-update)
  assets/
    config.json         — site-wide config: ttsBackend and player password hashes
  audio/
    voices/             — shared narrator voice file (.pt)
  [name]/
    session-N.html      — session narrative pages
    index.html          — campaign index
    world.html          — NPC/location reference
    sessions.json       — session list and audioEnabled flag
    assets/
      memoir-config.json  — character→player mapping for this campaign
      memoirs/            — public and encrypted private memoir JSON files
    audio/
      session-N/          — scene and memoir MP3s
      voices/             — locked voice prompt files (.pt) per character
```

---

## Getting Started

### Requirements
- [Claude Code](https://claude.ai/code)
- A campaign source file (adventure PDF converted to markdown, or your own notes)

### Setup

1. Clone this repository into a `.claude/` subdirectory inside your project folder (or wherever you prefer to keep it)
2. Open the project folder in Claude Code
3. Run `/dm-setup` — this creates `CLAUDE.md`, `.gitignore`, the shared `website/` infrastructure, and your first campaign folder
4. (Optional) Place source files in `campaigns/[name]/sources/` and run `/dm-index-campaign [name]` to shard them
5. Run `/dm-create-characters [name]` to set up the party
6. Run `/dm-start-session [name]` to begin

To pull framework updates later (new agent behaviour, JS fixes), run `git pull` inside the `.claude/` directory and then `/dm-update` to redeploy `CLAUDE.md`, `.gitignore`, and all JS/CSS files.

### PDF pre-processing (recommended)

PDFs read directly by Claude lose multi-column layout, table structure, and stat block formatting. Converting to markdown first with [marker-pdf](https://pypi.org/project/marker-pdf/) gives the indexer clean, structured input and produces significantly better encounter files.

```bash
pip install marker-pdf
```

Convert each PDF in your sources directory:

```bash
marker_single campaigns/[name]/sources/chapter-4.pdf --output_dir campaigns/[name]/sources/
```

This produces `chapter-4.md` alongside the PDF. The indexer reads `.md` files in preference to PDFs when both are present. You can delete or keep the PDFs after conversion — they are never modified.

For a whole directory at once:

```bash
marker campaigns/[name]/sources/ --output_dir campaigns/[name]/sources/
```

marker-pdf requires Python 3.9+. Run it on CPU to avoid GPU crashes — the surya-ocr models it uses can spike VRAM hard enough to crash the driver:

```bash
TORCH_DEVICE=cpu marker_single campaigns/[name]/sources/chapter-4.pdf --output_dir campaigns/[name]/sources/
```

Or use the provided batch script which handles this automatically:

```bash
./.claude/tools/convert-sources.sh [campaign-name]
```

### Running a session

Claude handles the flow automatically once the session starts. The DM's job is to:
- Describe what the players do
- Report dice roll results (players and DM roll real dice; Claude calculates)
- Make rulings — Claude supports, never overrides

At the end: `/dm-end-session` saves everything, writes the story, and updates the website.

---

## Rules Reference

The full D&D 5e SRD is included in `.claude/dnd-5e-srd/`. Claude never relies on training memory for mechanical rules — it always looks up spell effects, monster stats, and conditions from these files before stating them.

Additional house rules and format guides live in `.claude/rules/`:
- `combat-rules.md` — initiative, action economy, conditions, death saves
- `spellcasting.md` — slot tracking, concentration, ritual casting, component rules
- `items-and-loot.md` — treasure generation, attunement, magic item distribution
- `narration.md` — read-aloud vs DM-only formatting, player action narration
- `combat-log-format.md` — combat log file format
- `npc-log-format.md` — NPC conversation log file format

---

## Voice Generation Setup (Optional)

The audio system generates spoken narration and character dialogue for each session using a local open-source TTS model. Two backends are supported:

- **Qwen3-TTS** — used for voice auditioning (natural breathing and pacing)
- **MOSS-TTS** — used for final locked-voice generation (faster, more consistent output)

Each character gets a locked voice derived from a short self-introduction clip. Minor characters without a dedicated voice can be assigned a generic voice slot (e.g. `male-weathered-2`) via `party/voice-overrides.json`.

### Requirements

- Python 3.12 (via conda or pyenv — Python 3.14 is not supported by TTS dependencies)
- A CUDA-capable GPU (CPU generation works but is significantly slower)
- `ffmpeg` and `sox` installed on your system

### Installation

```bash
conda create -n tts python=3.12 -y
conda activate tts
pip install qwen-tts soundfile
```

For MOSS-TTS, follow the setup in `.claude/tools/backends/moss/`.

On Arch Linux:
```bash
sudo pacman -S ffmpeg sox
```

On Ubuntu/Debian:
```bash
sudo apt install ffmpeg sox
```

### How voices work

Each character needs an **introduction file** at `campaigns/[campaign]/info/introductions/[slug].md`. This file defines the character's voice descriptors and a first-person self-introduction that the model reads to generate a reference clip.

Example (`campaigns/waterdeep-dragon-heist/info/introductions/vajra-safahr.md`):
```markdown
---
name: Vajra Safahr
slug: vajra-safahr
gender: female
type: npc
age: mid-30s
voice:
  pitch: medium
  pace: brisk, efficient, no wasted syllables
  tone: direct, professional, mildly impatient with fools
  quality: clipped authority, someone who has too much to do and not enough time
  notes: Respectful but not warm until earned. Does not soften bad news.
---

Vajra Safahr, the Blackstaff. I protect this city — not the kind of protection that announces itself, but the kind that keeps you alive long enough to not notice it. I have resources, contacts, and a great deal of patience for competence. I have rather less patience for everything else. If you're here, you've already been evaluated. Let's not waste each other's time.
```

### Auditioning a voice

Use the `/dm-audition-voice` skill to generate 4 sample clips and lock in the best one:

```
/dm-audition-voice waterdeep-dragon-heist vajra-safahr
```

This will:
1. Create or update the introduction file interactively
2. Generate 4 voice samples using Qwen3-TTS VoiceDesign
3. Play them for you to evaluate
4. Lock in your choice as a reusable clone prompt at `website/[campaign]/audio/voices/[slug].pt`

The narrator voice (shared across all campaigns) lives at `website/audio/voices/narrator.pt` and is auditoned with `.claude/tools/audition-narrator.py`.

### Selecting a TTS backend

The backend is set per campaign in `campaigns/[name]/party/tts-backend`. Valid values are `qwen3` and `moss`. If the file is absent, `qwen3` is used by default.

You can also override the backend per-run with a flag:

```bash
# $TTS_PYTHON points at the Python interpreter in your TTS environment,
# e.g. export TTS_PYTHON=~/.conda/envs/tts/bin/python3.12
$TTS_PYTHON .claude/tools/generate-audio.py [campaign] [story-file] --backend moss
```

### Generating session audio

Use the `/dm-generate-audio` skill, or run the generator directly:

```bash
$TTS_PYTHON .claude/tools/generate-audio.py waterdeep-dragon-heist \
  campaigns/waterdeep-dragon-heist/party/session-7/session-7-story.md
```

This produces:
- One MP3 per scene chapter: `website/[campaign]/audio/session-N/01-scene-title.mp3`
- Two MP3s per character per memoir anchor — one public, one private:
  - `website/[campaign]/audio/session-N/memoir-[character]-[anchor]-public.mp3`
  - `website/[campaign]/audio/session-N/memoir-[character]-[anchor]-private.mp3`

Scene audio uses the narrator voice for prose and character voices for tagged dialogue lines. Memoir audio uses each character's own voice.

**Flags:**
- `--scenes-only` — skip memoir generation
- `--memoirs-only` — skip scene generation
- `--scene [N]` — regenerate only scene N
- `--backend [qwen3|moss]` — override the campaign's backend setting
- `--offline` — use local HuggingFace cache only (note: Qwen3-TTS requires a brief network check on load regardless)

Run sessions one at a time — running multiple TTS sessions in parallel can crash the GPU.

### Speaker tagging in stories

For character voices to appear in scene audio, dialogue in `session-N-story.md` must be tagged with the speaker's slug immediately before the quoted line:

```markdown
The halfling at the workbench looked up.

[ott-steelquill]: "We're closed. Who sent you?"

Caelith told him: Roxley, in the Dock Ward.
```

The story-teller agent produces these tags automatically when writing session stories. The slug must match a `.pt` file in `website/[campaign]/audio/voices/`.

### Audio player in the website

Session HTML pages include a small loudspeaker button on each chapter heading that plays the corresponding MP3. Memoir callouts show a play button when a player is logged in with their password — public memoir audio plays immediately, private memoir audio is unlocked by the character's password. Both are wired up automatically by the website-generator agent when it produces session HTML.

Audio buttons are only shown when `audioEnabled` is set to `true` in `website/[campaign]/sessions.json`. Set this once you have generated voice files for the campaign:

```json
{
  "audioEnabled": true,
  "sessions": [...]
}
```

Leave it `false` (the default for new campaigns) if you have not generated audio, so no broken play buttons appear.

---

## Credits

### Base project
This project is built on top of [claude-dungeon-master](https://github.com/PinchOfData/claude-dungeon-master) by PinchOfData. The original DM persona, the core instruction set for combat and NPCs, and the bundled 5e rulebook came from there. Everything beyond that (the additional sub-agents, the skills, the story/website/image/audio generation, and the campaign tooling) was added on top. Note: the upstream repository carries no explicit license; see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

### Image generation skill
The `ai-image-creator` skill is the open-source skill from [centminmod/my-claude-code-setup](https://github.com/centminmod/my-claude-code-setup) (MIT License), which handles model routing, reference images, and aspect ratios. The `scene-image-generator` agent that drives it, and the project-specific prompt rules, are my own.

### D&D 5e SRD
The System Reference Document is provided under the Open Gaming License v1.0a.

- **Original Content**: Wizards of the Coast, Inc.
- **SRD 5.0 Authors**: Mike Mearls, Jeremy Crawford, Chris Perkins, Rodney Thompson, Peter Lee, James Wyatt, Robert J. Schwalb, Bruce R. Cordell, Chris Sims, and Steve Townshend
- **Based on original material by**: E. Gary Gygax and Dave Arneson
- **Markdown conversion**: [Ben Morton](https://github.com/BTMorton/dnd-5e-srd) (MIT License, 2017)

## License

- Original DM system, agents, skills, scripts, and rules files: MIT License (see [`LICENSE`](LICENSE))
- Third-party components (base project, `ai-image-creator` skill, SRD): see [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)
- D&D 5e SRD content: Open Gaming License v1.0a (see `dnd-5e-srd/LICENSE`)
