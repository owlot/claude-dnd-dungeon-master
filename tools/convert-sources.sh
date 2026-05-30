#!/usr/bin/env bash
# Convert campaign source PDFs to markdown using marker-pdf (one at a time, GPU).
# Skips printer-friendly duplicates, poster maps, and printing guides.
# Usage: ./.claude/tools/convert-sources.sh [campaign-name]
#   default campaign: waterdeep-dragon-heist

CAMPAIGN="${1:-waterdeep-dragon-heist}"
SOURCES="campaigns/$CAMPAIGN/sources"
MARKER="${TTS_MARKER:-$(which marker_single 2>/dev/null)}"

if [ -z "$MARKER" ] || [ ! -f "$MARKER" ]; then
  echo "marker_single not found. Set TTS_MARKER to its path, or install with:"
  echo "  pip3 install marker-pdf"
  exit 1
fi

if [ ! -d "$SOURCES" ]; then
  echo "Sources directory not found: $SOURCES"
  exit 1
fi

# Find all PDFs, excluding printer-friendly variants, poster maps, and printing guides
mapfile -t PDFS < <(find "$SOURCES" -name "*.pdf" | grep -iv "printer.friendly\|printer friendly\|Printer Friendly\|-poster\|Printing_Guide" | sort)

TOTAL=${#PDFS[@]}
echo "Found $TOTAL PDFs to convert (skipping printer-friendly, poster, and guide files)"
echo ""

COUNT=0
SKIPPED=0
FAILED=0

for PDF in "${PDFS[@]}"; do
  COUNT=$((COUNT + 1))
  DIR=$(dirname "$PDF")
  BASENAME=$(basename "$PDF" .pdf)
  OUT_DIR="$DIR/$BASENAME"
  OUT_FILE="$OUT_DIR/$BASENAME.md"

  if [ -f "$OUT_FILE" ]; then
    echo "[$COUNT/$TOTAL] SKIP (already exists): $BASENAME"
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  echo "[$COUNT/$TOTAL] Converting: $BASENAME"
  if TORCH_DEVICE=cpu "$MARKER" "$PDF" --output_dir "$DIR" --disable_image_extraction 2>&1 | grep -E "Saved markdown|Error|error"; then
    echo "  -> OK: $OUT_FILE"
  else
    echo "  -> FAILED: $PDF"
    FAILED=$((FAILED + 1))
  fi
  echo ""
done

echo "================================"
echo "Done. $TOTAL PDFs processed."
echo "  Converted: $((TOTAL - SKIPPED - FAILED))"
echo "  Skipped (already done): $SKIPPED"
echo "  Failed: $FAILED"
