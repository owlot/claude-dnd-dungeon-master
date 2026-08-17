---
name: ai-image-creator
description: Generate PNG images using AI (multiple models via OpenRouter including Gemini, FLUX.2, Riverflow, SeedDream, GPT-5 Image, GPT-5.4 Image 2, proxied through Cloudflare AI Gateway BYOK — or fully locally via a running sd-webui-forge-neo instance, no API key, no per-image cost). Also analyze/describe existing images using multimodal AI vision (cloud providers only). Use when user asks to "generate an image", "create a PNG", "make an icon", "make it transparent", "generate locally", "use forge", "describe this image", "analyze this image", "what's in this image", "explain this image", or needs AI-generated visual assets for the project. Supports model selection via keywords (gemini, riverflow, flux2, seedream, gpt5, gpt5.4) or --provider forge for local generation, configurable aspect ratios/resolutions, transparent backgrounds (-t), reference image editing (-r), image analysis (--analyze), and per-project cost tracking (--costs).
allowed-tools: Bash, Read, Write
compatibility: Requires uv (Python runner). Cloud providers (openrouter/google) need network access and API keys configured in shell profile (~/.zshrc on macOS, ~/.bashrc on Linux, or System Environment Variables on Windows). The forge provider needs a running local sd-webui-forge-neo instance instead — no network or API key required.
metadata:
  tags: image-generation, ai, openrouter, cloudflare, gemini, flux2, riverflow, seedream, gpt5, gpt54, forge, local, stable-diffusion
---

# AI Image Creator

Generate PNG images via multiple AI models — routed through Cloudflare AI Gateway BYOK or directly via OpenRouter/Google AI Studio, **or** generated fully locally via a running `sd-webui-forge-neo` instance with `--provider forge`.

## Cloud vs. Local (Forge) — Decision Rule

Two independent choices: which **provider** (where generation happens) and, for cloud, which **model** (which cloud model to use).

| Choice | When to use |
|--------|-------------|
| **Cloud** (`--provider openrouter` / `google`, default) | User wants a specific named model (Gemini, FLUX.2, SeedDream, GPT-5 Image, etc.), needs reference-image editing (`-r`) or image analysis (`--analyze`), or no local Forge instance is running |
| **Local** (`--provider forge`) | User says "generate locally", "use forge", "no cost", "don't use the API", or a local Forge webui is already running and the user hasn't specified a cloud model — ask if unsure |

**Forge limitations to flag before using it:** no `--analyze` (no vision model), no `-r` reference images (txt2img only), no `--image-size` (use `-a` aspect ratio instead — mapped to fixed pixel sizes). If the user needs any of those, use a cloud provider instead.

**If the Forge webui isn't running**, tell the user to start it: `cd ~/Git/sd-webui-forge-neo && ./webui-user.sh` (takes ~15-20s to load) — don't attempt to start it yourself unless asked.

## Model Selection (cloud providers only)

When the user mentions a model keyword in their image request, use the corresponding `--model` flag:

| Keyword | Model | Use When User Says |
|---------|-------|--------------------|
| `gemini` | [Google Gemini 3.1 Flash](https://openrouter.ai/google/gemini-3.1-flash-image-preview) (default) | "gemini", "generate an image" (no model specified) |
| `riverflow` | [Sourceful Riverflow v2 Pro](https://openrouter.ai/sourceful/riverflow-v2-pro) | "riverflow", "use riverflow" |
| `flux2` | [FLUX.2 Max](https://openrouter.ai/black-forest-labs/flux.2-max) | "flux2", "flux", "use flux" |
| `seedream` | [ByteDance SeedDream 4.5](https://openrouter.ai/bytedance-seed/seedream-4.5) | "seedream", "use seedream" |
| `gpt5` | [OpenAI GPT-5 Image](https://openrouter.ai/openai/gpt-5-image) | "gpt5", "gpt5 image", "use gpt5" |
| `gpt5.4` | [OpenAI GPT-5.4 Image 2](https://openrouter.ai/openai/gpt-5.4-image-2) | "gpt5.4", "gpt-5.4 image", "use gpt5.4" |

For local generation, pass `--provider forge`. Use `-m krea2` (default) or `-m flux` to pick which local checkpoint to generate with — see the Local Generation section below for details.

## Instructions

> **Environment:** Always prefix every `uv run` command with `set -a && source .env && set +a &&` to load the project API keys. Example: `set -a && source .env && set +a && uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py ...`. The `.env` file is project-specific and is never sourced automatically.

> **Routing check:** If the user asks to **describe, analyze, or explain an existing image** (not generate a new one), skip directly to the **Image Analysis (`--analyze`)** section below. No prompt enhancement or output path needed.

### Step 1: Write Prompt

For long or complex prompts (recommended), write to `${CLAUDE_SKILL_DIR}/tmp/prompt.txt` using the Write tool:

```
Write prompt text to ${CLAUDE_SKILL_DIR}/tmp/prompt.txt
```

For short prompts (under 200 chars, no special characters), pass inline via `--prompt`.

**CRITICAL — Prompt Quality Tips:**
- Be detailed and descriptive. Include style, colors, composition, background, and intended use.
- Good: "A flat-design globe icon with vertical timezone band lines in blue and teal, white background, clean vector style, suitable for a web app at 512x512 pixels"
- Bad: "globe icon"
- Specify "transparent background" or "white background" explicitly.
- For icons, mention the target size (e.g., "512x512", "favicon at 32x32").
- For photos, describe lighting, camera angle, and mood.

### Step 1.5: Prompt Enhancement (Optional — Progressive Disclosure)

Professional prompt patterns are available in 3 reference files. These are **not loaded by default** — only read them when the user's request matches a category or they explicitly ask for enhancement.

**Category Detection** — Match the user's request to a category:

| If request mentions... | Category | Also read |
|----------------------|----------|-----------|
| "product shot", "product photo", "hero image" | `product_hero` | `prompt-core.md` + `prompt-categories.md` § product_hero |
| "lifestyle", "in-use", "in context" | `lifestyle` | `prompt-core.md` + `prompt-categories.md` § lifestyle |
| "instagram", "social media", "tiktok", "pinterest" | `social_media` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § social_media |
| "banner", "ad", "email header" | `marketing_banner` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § marketing_banner. **Routing hint:** If user has an existing logo and wants multiple standard sizes → use composite mode instead (see `## Composite Banners`). |
| "website", "app", "logo", "ad format", "leaderboard", "skyscraper" | `web_app` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § web_app. **Routing hint:** For "logo banners" or "OG images with my logo" where user has existing logo → use `composite-banners.py`. For "design me a new logo" → use `generate-image.py`. |
| "brand kit", "logo banners", "banner sizes", "IAB sizes", "consistent banners" + user has existing logo | `composite` | Read `references/composite-reference.md`, use `composite-banners.py` |
| "icon", "favicon", "app icon" | `icon_logo` | `prompt-core.md` + `prompt-categories.md` § icon_logo |
| "mascot", "character", "illustration", "artwork" | `illustration` | `prompt-core.md` + `prompt-categories.md` § illustration |
| "food", "drink", "recipe", "restaurant" | `food_drink` | `prompt-core.md` + `prompt-categories.md` § food_drink |
| "building", "interior", "room", "architecture" | `architecture` | `prompt-core.md` + `prompt-categories.md` § architecture |
| "chart", "infographic", "data", "diagram" | `infographic` | `prompt-core.md` + `prompt-categories.md` § infographic |
| "t-shirt", "mug design", "poster", "POD", "print-on-demand" | `pod_design` | `prompt-core.md` + `prompt-platforms.md` + `prompt-categories.md` § pod_design |
| "describe", "analyze", "what's in this image", "explain image" | `analyze` | Skip prompt enhancement — use `--analyze` mode directly. Read `references/analyze-reference.md` for advanced analysis patterns |
| No match / simple request | — | Skip patterns, generate directly |

**When to skip enhancement:**
- User's prompt is already detailed (150+ words with camera/lighting/composition specifics)
- Simple/direct requests ("generate a blue circle on white background")
- User says "no pattern" or provides a fully formed prompt

**When to apply:**
- User says "use product_hero pattern" or "apply social_media pattern" (explicit)
- Request clearly matches a category above (auto-detect)
- User asks for "enhanced prompt" or "professional quality"

**Reference files** (in `references/` directory):
- `prompt-core.md` — Foundational rules: narrative prompting, camera/lens/lighting specs, text rendering rules, model recommendations
- `prompt-platforms.md` — Social media ratios, IAB ad sizes, web dimensions, POD specs — all mapped to `-a`/`-s` flags
- `prompt-categories.md` — 11 category formulas with templates and complete example prompts

### Step 2: Run Generation Script

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  [--provider openrouter|google|forge] \
  [-a "16:9"] \
  [-s "2K"] \
  [-m "model-id"] \
  [-r "ref-image.png"] \
  [-t]
```

With a specific model:
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  -m riverflow \
  -p "A serene mountain lake at sunset"
```

Locally, no API key or cost (requires the Forge webui already running with `--api`):
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  --provider forge \
  -a "16:9" \
  -p "A serene mountain lake at sunset"
```

With transparent background (requires ffmpeg + imagemagick):
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "mascot.png" \
  -t \
  -p "A friendly robot mascot character"
```

With reference image for editing/style transfer (multimodal models only):
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "edited.png" \
  -r "original.png" \
  -p "Change the background to a sunset scene"
```

Or with inline prompt (default model):
```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  -p "A simple blue circle on white background"
```

### Step 3: Clean Up (if temp file used)

```bash
rm -f ${CLAUDE_SKILL_DIR}/tmp/prompt.txt
```

### Step 4: Verify Output

```bash
file OUTPUT_PATH
```

Confirm it shows "PNG image data" and report the file path and size to the user.

### Step 5: Post-Processing (optional)

If the user needs resizing, format conversion, or other manipulation, first detect available image tools, then use them. See **Image Tools** section below.

## Parameters

| Argument | Short | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `--output` | `-o` | Yes | -- | Output file path (parent dirs auto-created) |
| `--prompt` | `-p` | No | -- | Inline prompt text |
| `--prompt-file` | -- | No | `../tmp/prompt.txt` | Path to prompt file |
| `--provider` | -- | No | `openrouter` | `openrouter`, `google`, or `forge` (local, no API key/cost) |
| `--aspect-ratio` | `-a` | No | model default | OpenRouter: `1:1`, `16:9`, `9:16`, `3:2`, `2:3`, `4:3`, `3:4`, `4:5`, `5:4`, `21:9`. Forge: `1:1`, `16:9`, `9:16`, `3:2`, `2:3`, `4:3`, `3:4` (mapped to fixed pixel sizes) |
| `--image-size` | `-s` | No | model default | OpenRouter only: `0.5K`, `1K`, `2K`, `4K`. Not supported with `--provider forge` |
| `--model` | `-m` | No | `gemini` (cloud) / `krea2` (forge) | Cloud: keyword (`gemini`, `riverflow`, `flux2`, `seedream`, `gpt5`) or full model ID. Forge: `krea2` or `flux` preset name |
| `--ref` | `-r` | No | -- | Reference image file (repeatable). For editing/style transfer. Multimodal models only (gemini, gpt5). Not supported with `--provider forge` |
| `--analyze` | -- | No | -- | Analyze/describe a reference image (text-only output, no image generated). Requires `-r`. Multimodal models only. Not supported with `--provider forge` |
| `--transparent` | `-t` | No | -- | Generate with transparent background. Requires ffmpeg + imagemagick |
| `--costs` | -- | No | -- | Display generation/cost history for this project and exit |
| `--list-models` | -- | No | -- | List available model keywords and exit |

## Environment Variables

| Variable | Required For | Description |
|----------|-------------|-------------|
| `AI_IMG_CREATOR_CF_ACCOUNT_ID` | Gateway mode | Cloudflare account ID |
| `AI_IMG_CREATOR_CF_GATEWAY_ID` | Gateway mode | AI Gateway name |
| `AI_IMG_CREATOR_CF_TOKEN` | Gateway mode | Gateway auth token |
| `AI_IMG_CREATOR_OPENROUTER_KEY` | Direct OpenRouter | OpenRouter API key (`sk-or-...`) |
| `AI_IMG_CREATOR_GEMINI_KEY` | Direct Google | Google AI Studio API key |

Gateway mode activates when all 3 `CF_*` vars are set. Falls back to direct mode if gateway fails.

For first-time setup, see `references/setup-guide.md`.

## Local Generation (`--provider forge`)

Generates images on a running local `sd-webui-forge-neo` instance instead of any cloud API — no API key, no network dependency, no per-image cost. Uses the Forge/A1111-compatible `/sdapi/v1/txt2img` REST endpoint directly.

**Prerequisite:** the webui must already be running with `--api` (set in `webui-user.sh`'s `COMMANDLINE_ARGS`). If it's not running:

```bash
cd ~/Git/sd-webui-forge-neo && ./webui-user.sh
```

It takes ~15-20s to load. Check readiness with `grep -q "Running on local URL" <logfile>` before generating, or just try a generation and read the error if it fails.

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" \
  --provider forge \
  -a "16:9" \
  -p "A cinematic fantasy tavern interior, warm candlelight"
```

**Two checkpoint presets, selected with `-m`/`--model` (default: `krea2`):**

| Preset | Checkpoint | Notes |
|--------|-----------|-------|
| `krea2` (default) | Krea-2-Raw | Faster, more painterly-leaning results |
| `flux` | FLUX.2-klein-9B | Sharper, more photorealistic — slightly slower |

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "OUTPUT_PATH" --provider forge -m flux -a "3:4" -p "..."
```

**Config (env vars, all optional — sensible defaults already point at this project's Forge setup):**

| Variable | Default | Description |
|----------|---------|--------------|
| `AI_IMG_CREATOR_FORGE_URL` | `http://127.0.0.1:7860` | Base URL of the running webui |
| `AI_IMG_CREATOR_FORGE_CHECKPOINT` | (preset's checkpoint) | Overrides the checkpoint filename for either preset |
| `AI_IMG_CREATOR_FORGE_MODULES` | (preset's VAE + text encoder paths) | Comma-separated absolute paths to additional modules (VAE, text encoder) the checkpoint needs — overrides the whole list |

**Known gotcha #1 — empty negative prompt crashes Krea-2:** never send an explicit empty `negative_prompt` to the Krea-2 checkpoint — it crashes the Qwen3VL text encoder (0-element tensor reshape error). The script already omits this field; if you ever call the raw API directly (e.g. via `curl`), leave `negative_prompt` out entirely rather than passing `""`.

**Known gotcha #2 — module files must live in `models/VAE/` or `models/text_encoder/`:** Forge's additional-module list (used by both presets above) is only populated by scanning `models/VAE/` and `models/text_encoder/` (or `--vae-dir`/`--text-encoder-dir`) at webui startup. A VAE or text-encoder file sitting inside a checkpoint's own subfolder (e.g. `models/Stable-diffusion/SomeModel/vae/...`) is silently dropped from the request even if you pass its exact path — the API call still returns 200, but that module never actually loads, and you'll get a confusing "You do not have VAE/Qwen3 state dict!" error instead. If you add a new preset, copy (or symlink) its VAE/text-encoder file into `models/VAE/` or `models/text_encoder/` first. Multi-shard HuggingFace text encoders (multiple `model-0000N-of-0000N.safetensors` files) also need pre-merging into a single safetensors file before use — Forge's module loader has no logic to reassemble shards on its own.

**Not supported in forge mode:** `--analyze` (no vision model), `-r` reference images (txt2img only, no image-to-image or editing), `--image-size` (use `-a` instead). Attempting any of these exits with an error before a request is made.

## Transparent Mode (`-t`)

Generates images with transparent backgrounds using a 3-step pipeline:

1. **Green screen generation** — Prompt is augmented to place subject on solid #00FF00 green
2. **FFmpeg chroma key** — Removes green background + green fringe from edges
3. **ImageMagick auto-crop** — Trims transparent padding

**Requirements:** `brew install ffmpeg imagemagick`

**Use cases:** Game sprites, icons, logos, mascots, marketing assets with transparency.

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "sprite.png" -t -p "A pixel art treasure chest"
```

## Reference Images (`-r`)

Send existing images alongside text prompts for editing, style transfer, or guided generation. Supports multiple references. **Multimodal models only** (gemini, gpt5) — image-only models (riverflow, flux2, seedream) will error.

```bash
# Edit an existing image
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "edited.png" -r "photo.png" -p "Make the background white"

# Style transfer with multiple references
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  -o "combined.png" -r "style1.png" -r "content.png" -p "Apply the style of the first image to the second"
```

Supported formats: PNG, JPEG, WebP, GIF.

## Image Analysis (`--analyze`)

Describe, analyze, or explain existing images using multimodal AI vision. Returns text-only output (no image generated). **Multimodal models only** (gemini, gpt5).

No `-o` output path needed. No prompt enhancement needed. The script outputs JSON to stdout with the model's analysis in the `analysis` field.

```bash
# Analyze with default prompt (describes subject, style, colors, composition, mood, text)
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "photo.png"

# Analyze with custom prompt
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "photo.png" -p "Describe this image in plain text and also in JSON structured output"

# Analyze with a specific model
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "photo.png" -m gpt5 -p "What text is visible in this image?"

# Analyze multiple images together
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py \
  --analyze -r "before.png" -r "after.png" -p "Compare these two images and describe the differences"
```

**JSON output format:**

```json
{"ok": true, "analyze": true, "analysis": "<model text>", "provider": "openrouter", "model": "...", "mode": "gateway", "elapsed_seconds": 3.2, "ref_images": 1}
```

**Incompatible flags:** `--analyze` cannot be combined with `-o`, `-t`, `-a`, or `-s`.

For advanced analysis prompt patterns (structured output, comparison, targeted analysis), read `references/analyze-reference.md`.

## Cost Tracking (`--costs`)

Every generation is logged to `.ai-image-creator/costs.json` in your project directory. View history:

```bash
uv run python ${CLAUDE_SKILL_DIR}/scripts/generate-image.py --costs
```

Shows per-model breakdown: generation count, total tokens, elapsed time, and recent entries. **Security:** Only non-sensitive data is logged (model, tokens, timing, file path). No API keys or credentials are ever stored.

Consider adding `.ai-image-creator/` to your `.gitignore`.

## Composite Banners

Generate consistent logo banners across multiple sizes from a JSON config. Uses ImageMagick for offline compositing — no API calls, no network required. Composites an existing logo/mark onto branded backgrounds with text at standard dimensions.

### Composite vs. AI Generation — Decision Rule

Use **composite-banners.py** when ALL of these are true:
- User has an existing logo/mark they want to use as-is (provides or references a logo file)
- User wants consistent branding across multiple standard sizes (not one creative image)
- The output is logo + text on a solid/gradient background (not a photograph, illustration, or creative design)

Use **generate-image.py** (AI generation) when ANY of these are true:
- User wants a creative/artistic banner design (describes a scene, mood, concept, or style)
- User wants AI to design the visual content (product shots, illustrations, creative layouts)
- User wants a single banner with artistic content, not a multi-size brand kit

**When composite mode applies**, read `references/composite-reference.md` for full config schema, preset dimensions, and font handling details.

### Quick Start

1. **Init config:** `uv run python ${CLAUDE_SKILL_DIR}/scripts/composite-banners.py --init`
2. **Edit** `banner-config.json` — set logo path, brand text, colors, banner sizes
3. **Validate:** `uv run python ${CLAUDE_SKILL_DIR}/scripts/composite-banners.py --validate`
4. **Generate:** `uv run python ${CLAUDE_SKILL_DIR}/scripts/composite-banners.py -c banner-config.json -o ./banners/`

### Composite Parameters

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--config` | `-c` | `banner-config.json` | Config JSON path |
| `--output-dir` | `-o` | `.` | Output directory |
| `--name` | `-n` | all | Generate single banner by name |
| `--format` | `-f` | `png` | `png`, `webp`, `jpeg` |
| `--list-presets` | | | List IAB/social/web size presets |
| `--init` | | | Generate starter config |
| `--validate` | | | Check config, exit 0 or 2 |
| `--dry-run` | | | Preview without rendering |
| `--json` | | | Structured JSON to stdout |
| `--verbose` | `-v` | | Verbose output |

**Requirements:** ImageMagick 7 (`brew install imagemagick` or `apt install imagemagick`).

### Workflow Hints

**Starting composite mode:**
- Ask user for: logo file path, brand name, tagline text, brand colors (hex)
- If user doesn't have a logo yet → use generate-image.py to create one first
- Run `--init` to scaffold config, then help user fill in their brand values

**During generation:**
- Always run `--validate` before generating to catch font/logo issues early
- Use `--name` to iterate on one banner before generating the full set
- Show user 3-4 representative sizes (hero, OG, square, leaderboard) for approval

**After generation:**
- If user wants creative/artistic redesign of banner visuals → switch to generate-image.py (composite only does logo + text on gradient/solid backgrounds)
- If banners look too plain → suggest AI-generating a textured or photographic background first, then compositing the logo onto it

**Combined workflow (most powerful):**
1. Use generate-image.py to AI-create a hero background or textured pattern
2. Use composite-banners.py to overlay the logo + text onto that background at all standard sizes
This gives both creative AI visuals AND pixel-perfect logo consistency.

## Image Tools

On first invocation, detect available image manipulation tools:

```bash
which magick convert sips ffmpeg 2>/dev/null
```

### Available Tools

| Tool | Check | Key Operations |
|------|-------|----------------|
| **ImageMagick 7** (`magick`) | `magick --version` | Resize, crop, convert, composite |
| **ImageMagick 6** (`convert`) | `convert --version` | Same ops, legacy command name |
| **sips** (macOS) | `sips --help` | Resize, format conversion |
| **ffmpeg** | `ffmpeg -version` | Convert formats, resize |

### Common Post-Processing

```bash
# Resize
magick output.png -resize 512x512 icon-512.png

# Multiple sizes (icons)
for s in 16 32 48 64 128 256 512; do magick output.png -resize ${s}x${s} icon-${s}.png; done

# Convert to WebP
magick output.png output.webp

# Maskable icon (add safe-zone padding)
magick output.png -gravity center -extent 120%x120% maskable.png

# macOS sips resize
sips --resampleWidth 512 --resampleHeight 512 output.png --out icon-512.png
```

CRITICAL: Check tool availability before using. Prefer `magick` (IM7) over `convert` (IM6). If no tools found, inform user: `brew install imagemagick`.

## Common Issues

### "No API credentials configured"
**Cause:** Environment variables not set or not exported.
**Fix:** Add exports to `~/.zshrc` and run `source ~/.zshrc`. See `references/setup-guide.md`.

### "HTTP 401: Unauthorized"
**Cause:** Invalid or expired API key/token.
**Fix:** Check `AI_IMG_CREATOR_CF_TOKEN` (gateway) or `AI_IMG_CREATOR_OPENROUTER_KEY` (direct). Regenerate if needed.

### "No images in response"
**Cause:** Model returned text only (safety filter, unclear prompt, or unsupported request).
**Fix:** Make the prompt more specific and descriptive. Avoid prohibited content.

### "Connection error" / timeout
**Cause:** Network issue or image generation taking too long (120s timeout).
**Fix:** Retry. If persistent, try `--provider google` as alternative. Check CF gateway status.

## Detailed API Reference

For full API formats, response schemas, BYOK configuration, and curl examples:
see [references/api-reference.md](references/api-reference.md)

For first-time setup instructions:
see [references/setup-guide.md](references/setup-guide.md)
