# Platform & Format Specifications

Aspect ratio mappings, ad format sizes, and print-on-demand specs. Read this when the user mentions a specific platform, ad format, or output dimension.

---

## Social Media Aspect Ratios

| Platform / Use | Aspect Ratio | `-a` Flag | `-s` Size | Prompt Hint |
|---------------|-------------|-----------|-----------|-------------|
| Instagram feed | 4:5 | `-a 4:5` | `-s 1K` | "vertical social post format" |
| Instagram story / Reels | 9:16 | `-a 9:16` | `-s 1K` | "vertical full-screen story format" |
| Instagram square | 1:1 | `-a 1:1` | `-s 1K` | "square format" |
| Facebook feed | 4:5 or 1:1 | `-a 4:5` | `-s 1K` | "social media feed format" |
| Facebook cover | 16:9 | `-a 16:9` | `-s 2K` | "widescreen cover format" |
| Pinterest pin | 2:3 | `-a 2:3` | `-s 1K` | "tall vertical pin format" |
| TikTok thumbnail | 9:16 | `-a 9:16` | `-s 1K` | "vertical video thumbnail format" |
| YouTube thumbnail | 16:9 | `-a 16:9` | `-s 2K` | "widescreen landscape format" |
| LinkedIn post | 1:1 or 4:5 | `-a 1:1` | `-s 1K` | "professional social post" |
| X / Twitter post | 16:9 | `-a 16:9` | `-s 1K` | "widescreen post format" |

---

## Web / App Ad Formats (IAB Standard)

Standard ad sizes mapped to the closest supported `-a` flag value. Most require post-generation cropping to exact pixel dimensions.

| Ad Format | Pixels | Closest `-a` | `-s` Size | Post-Processing |
|-----------|--------|-------------|-----------|-----------------|
| Leaderboard | 728×90 | `-a 4:1` | `-s 1K` | Crop to 728×90 |
| Billboard | 970×250 | `-a 4:1` | `-s 2K` | Crop to 970×250 |
| Medium Rectangle | 300×250 | `-a 5:4` | `-s 1K` | Crop to 300×250 |
| Large Rectangle | 336×280 | `-a 5:4` | `-s 1K` | Crop to 336×280 |
| Half Page | 300×600 | `-a 1:2` † | `-s 1K` | Crop to 300×600 |
| Skyscraper | 160×600 | `-a 1:4` | `-s 1K` | Crop to 160×600 |
| Wide Skyscraper | 300×600 | `-a 1:2` † | `-s 1K` | Crop to 300×600 |
| Mobile Banner | 320×50 | `-a 4:1` | `-s 1K` | Crop to 320×50 |
| Mobile Interstitial | 320×480 | `-a 2:3` | `-s 1K` | Crop to 320×480 |

† 1:2 may not be supported by all models. Use `-a 9:16` and crop as fallback.

### Ad Format Prompt Tips

- **Reserve negative space** for text overlay — "Product positioned in left third with large clean area on right for headline and CTA"
- **High contrast** at small sizes — ad banners are often viewed small; bold colors and clear focal points matter
- **CTA zone** — "Clear call-to-action zone in lower-right corner"
- **Brand consistency** — Specify brand colors by description: "deep navy blue and bright amber accent"

---

## Standard Web Dimensions

| Asset | Pixels | `-a` Flag | Notes |
|-------|--------|-----------|-------|
| OG / social share | 1200×630 | `-a 16:9` | Slight crop to 1200×630 |
| Favicon | 32×32, 16×16 | `-a 1:1` `-s 0.5K` | Generate larger, resize down with `magick -resize` |
| App icon (iOS) | 1024×1024 | `-a 1:1` `-s 1K` | Must be square, no transparency |
| App icon (Android) | 512×512 | `-a 1:1` `-s 1K` | Can include transparency with `-t` |
| Apple Touch icon | 180×180 | `-a 1:1` `-s 0.5K` | Generate larger, resize down |
| Email header | ~600×200 | `-a 3:1` † | Crop to exact width |
| Hero banner | 1920×600 | `-a 3:1` † | Or `-a 16:9` and crop height |
| Website logo | varies | `-a 3:1` or `-a 4:1` | Generate wide, trim to content |

† 3:1 is not a standard `-a` flag value. Use `-a 21:9` (≈2.33:1) as closest option and crop.

### Web Asset Prompt Tips

- **Favicons/icons**: "Simple, recognizable silhouette at small size. Bold shape, maximum 2 colors, no fine detail."
- **OG images**: Include clear text area — social platforms overlay title and description.
- **Logos**: "Clean vector-style logo on solid background. Simple shapes, readable at 32px."
- **Hero banners**: Compose with text overlay in mind — push subject to one side.

---

## Print-on-Demand Specs

| Product | Print Area (px) | Aspect Ratio | `-a` Flag | Notes |
|---------|----------------|-------------|-----------|-------|
| T-shirt front | 4500×5400 | ~5:6 | `-a 4:5` | Center-chest or full-front placement |
| T-shirt back | 4500×5400 | ~5:6 | `-a 4:5` | Full back design |
| Mug wrap (11oz) | 2700×1100 | ~11:4.5 | `-a 21:9` | Wide horizontal, wraps around cylinder |
| Mug wrap (15oz) | 2700×1100 | ~11:4.5 | `-a 21:9` | Same wrap, slightly taller |
| Poster (18×24) | 5400×7200 | 3:4 | `-a 3:4` | Vertical orientation |
| Poster (24×36) | 7200×10800 | 2:3 | `-a 2:3` | Vertical orientation |
| Phone case | varies | ~9:19 | `-a 9:16` | Tall narrow, avoid bottom edge (camera cutout) |
| Tote bag | 3600×3600 | 1:1 | `-a 1:1` | Square print area |
| Sticker | varies | 1:1 | `-a 1:1` | Die-cut friendly: bold silhouette + `-t` for transparency |

### POD Prompt Tips

- **Always use solid background** for easy removal: pure black `#000000` or pure white `#FFFFFF`
- Or use `-t` (transparent mode) to generate with alpha channel directly
- **Sharp edges** between design and background — "no gradients, no ambient shadows, no noise at edges"
- **Print-ready isolation** — "design element isolated on [color] background, optimized for production printing"
- **T-shirt placement**: Describe collar reference — "positioned 3-4 inches below the neckline" not just "center"
