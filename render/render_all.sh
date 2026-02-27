#!/usr/bin/env bash
# Batch-render all .xosc scenarios
# Usage: ./render_all.sh [xosc-dir] [output-dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
XOSC_DIR="${1:-$SCRIPT_DIR/../generator/output}"
OUTPUT_DIR="${2:-$SCRIPT_DIR/output}"

if [ -z "${ESMINI_HOME:-}" ]; then
  echo "ERROR: Set ESMINI_HOME environment variable"
  echo "  export ESMINI_HOME=/path/to/esmini"
  exit 1
fi

TOTAL=0
SUCCESS=0
FAILED=0

echo "=== RFS Scenario Render Pipeline ==="
echo "XOSC dir:   $XOSC_DIR"
echo "Output dir: $OUTPUT_DIR"
echo "esmini:     $ESMINI_HOME"
echo ""

for xosc in "$XOSC_DIR"/*.xosc; do
  [ -f "$xosc" ] || continue
  TOTAL=$((TOTAL + 1))
  if "$SCRIPT_DIR/render_one.sh" "$xosc" "$OUTPUT_DIR"; then
    SUCCESS=$((SUCCESS + 1))
  else
    FAILED=$((FAILED + 1))
    echo "   FAILED: $(basename "$xosc")"
  fi
  echo ""
done

echo "=== Done: $SUCCESS/$TOTAL succeeded, $FAILED failed ==="
