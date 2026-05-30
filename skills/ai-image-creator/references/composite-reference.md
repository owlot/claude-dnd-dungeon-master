# Composite Banners — Reference

Full config schema, presets, font handling, and workflow details for `composite-banners.py`. Read this when composite mode is detected (user has existing logo + wants multiple standard sizes).

---

## Config File Schema

The config JSON has four top-level sections: `logo`, `brand`, `fonts`, `banners`.

### `logo` — Source image and extraction mode

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | `"logo.png"` | Path to logo image, **relative to the config file's directory** |
| `mode` | string | `"full"` | `"full"` = use entire image; `"extract"` = crop a sub-region |
| `crop` | object | — | `{"x", "y", "w", "h"}` pixel coordinates (required when `mode="extract"`) |
| `background` | string | `"white"` | `"white"` = remove white bg with fuzz; `"transparent"` = already has alpha; `"none"` = use as-is |
| `fuzz` | string | `"15%"` | ImageMagick fuzz tolerance for white background removal |
| `aspect_ratio` | array\|null | `null` | `[width, height]` explicit ratio, or `null` to auto-detect from image dimensions |

**When to use each mode:**
- `"full"` — Most common. Your logo is already the complete mark you want on banners. No cropping needed.
- `"extract"` — Your logo file contains a larger image (e.g., logo + text + whitespace) and you want to crop to just the icon/mark portion. Provide pixel coordinates in `crop`.

**When to use each background option:**
- `"white"` — Logo is on a white background (common for downloaded logos). The script removes white pixels with fuzz tolerance.
- `"transparent"` — Logo PNG already has an alpha channel. Skip background removal entirely.
- `"none"` — Use the image exactly as-is, including its background. Useful for logos on colored backgrounds you want to keep.

### `brand` — Text content and colors

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | required | Primary text (brand name). Rendered in title font. |
| `tagline` | string | `""` | Secondary text below/beside title |
| `url_text` | string\|null | `null` | Optional 3rd line (website URL, CTA). `null` to disable. |
| `title_color` | hex string | `"#ffffff"` | Title text color |
| `tagline_color` | hex string | `"#b0b8cc"` | Tagline text color |
| `url_color` | hex string | `"#8090aa"` | URL text color |
| `background` | object | — | Gradient: `{"start": "#hex", "end": "#hex"}` or solid: `{"color": "#hex"}` |

### `fonts` — Ordered fallback lists

Each role has an array of font candidates. The script tries each in order and uses the first available on the system. Supports both ImageMagick font names and absolute file paths.

```json
"fonts": {
  "title":   ["Arial-Bold", "DejaVu-Sans-Bold", "Liberation-Sans-Bold"],
  "tagline": ["Arial", "DejaVu-Sans", "Liberation-Sans"],
  "url":     ["Arial", "DejaVu-Sans", "Liberation-Sans"]
}
```

**How resolution works:**
1. Script calls `magick -list font` once (cached) to get all system fonts
2. For each candidate: if it starts with `/`, checks file exists; otherwise checks the font name set
3. Uses the first match, warns to stderr if it fell back from the preferred font
4. Exits with error if no font is found for `title` or `tagline`

**Cross-platform defaults:**
- macOS: `Arial-Bold`, `Helvetica-Neue-Condensed-Bold`, `Avenir-Next-Condensed-Heavy`
- Linux: `DejaVu-Sans-Bold`, `Liberation-Sans-Bold`
- Both: `Arial-Bold` (usually available on both via fontconfig)

Run `magick -list font | grep Font:` to see available fonts on your system.

### `banners` — Array of banner definitions

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | required | Output filename (without extension). Must be unique. |
| `width` | int | required | Banner width in pixels |
| `height` | int | required | Banner height in pixels |
| `category` | string | `""` | Grouping label for display (e.g., `"iab"`, `"social"`, `"website"`) |
| `layout` | string | required | `"horizontal"`, `"horizontal-compact"`, or `"centered"` |
| `logo_height_pct` | number | varies | Logo height as percentage of banner height |
| `title_size_pct` | number | varies | Title font size as percentage of banner height |
| `tagline_size_pct` | number | `0` | Tagline font size as percentage. `0` = omit tagline. |
| `url_size_pct` | number | `0` | URL text font size as percentage. `0` = omit URL. |

---

## Layout Types

### `horizontal` — Logo left, text right
Best for: wide banners (hero, billboard, social covers, email headers).
Logo positioned on the left with padding, title + tagline + optional URL stacked vertically to the right.

### `horizontal-compact` — Single-line icon + title
Best for: ultra-thin banners (leaderboard 728x90, mobile 320x50).
Logo icon and title on one line. Tagline to the right of title if space allows.

### `centered` — Logo above, text below
Best for: square/portrait formats (OG images, square logos, half-page ads, skyscrapers).
Logo centered above, title + tagline + optional URL centered below in a vertical stack.

---

## Preset Dimensions

Run `--list-presets` to see all available presets with recommended layouts and sizing. These are reference values — copy the dimensions and layout into your config's `banners` array.

### IAB Standard Ad Sizes
| Preset | Pixels | Layout |
|--------|--------|--------|
| `iab-leaderboard` | 728x90 | horizontal-compact |
| `iab-billboard` | 970x250 | horizontal |
| `iab-medium-rectangle` | 300x250 | centered |
| `iab-large-rectangle` | 336x280 | centered |
| `iab-half-page` | 300x600 | centered |
| `iab-skyscraper` | 160x600 | centered |
| `iab-mobile-banner` | 320x50 | horizontal-compact |
| `iab-mobile-interstitial` | 320x480 | centered |

### Social Media
| Preset | Pixels | Layout |
|--------|--------|--------|
| `social-twitter-header` | 1500x500 | horizontal |
| `social-linkedin-banner` | 1584x396 | horizontal |
| `social-facebook-cover` | 1640x624 | horizontal |
| `social-youtube-banner` | 2560x1440 | centered |

### Web Assets
| Preset | Pixels | Layout |
|--------|--------|--------|
| `web-hero` | 1920x600 | horizontal |
| `web-og-social` | 1200x630 | centered |
| `web-email-header` | 600x200 | horizontal |
| `web-square-logo` | 512x512 | centered |
| `web-favicon` | 256x256 | centered |

---

## Combined Workflow: AI + Composite

The most powerful workflow uses both scripts together:

1. **AI-generate** a creative background or textured pattern:
   ```bash
   uv run python SCRIPT_PATH/generate-image.py \
     -o "hero-bg.png" -a "16:9" -s "2K" \
     -p "Abstract dark gradient with subtle geometric tech patterns, deep navy to indigo"
   ```

2. **Create a banner config** pointing to your logo with your brand details

3. **Composite** the logo + text onto branded backgrounds at all standard sizes:
   ```bash
   uv run python SCRIPT_PATH/composite-banners.py \
     -c banner-config.json -o ./banners/ --json
   ```

This gives both creative AI visuals AND pixel-perfect logo consistency across all sizes.

---

## After Generation — Next Steps

- **Banners look too plain:** Suggest generating an AI background with `generate-image.py` and using it as a background in the composite config (the config's gradient background can be swapped for a richer visual).
- **Color inconsistency between banners:** This is the exact problem composite mode solves. If you see inconsistency, banners may be mixing AI-generated and composite outputs. Regenerate all from one config.
- **Want to change brand colors:** Edit `brand.background` and `brand.*_color` values, then regenerate. All banners update consistently in one run.
- **Need different sizes:** Run `--list-presets` to see standard sizes. Add entries to the `banners` array.
- **Iterate on one banner:** Use `--name banner-name` to regenerate just that one without re-rendering all.
- **Need WebP for web performance:** Use `--format webp` to output all banners as WebP instead of PNG.
