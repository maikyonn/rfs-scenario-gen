#!/usr/bin/env bash
# Renders a single .xosc scenario to MP4 + thumbnail
# Usage: ./render_one.sh <path-to-xosc> [output-dir]
#
# Requires: ESMINI_HOME set, ffmpeg installed
# Note: esmini opens a viewer window for capture (cannot be headless)

set -euo pipefail

XOSC_FILE="$(cd "$(dirname "${1:?Usage: render_one.sh <xosc-file> [output-dir]}")" && pwd)/$(basename "$1")"
OUTPUT_DIR="$(cd "${2:-$(dirname "$0")/output}" 2>/dev/null && pwd || echo "${2:-$(dirname "$0")/output}")"
ESMINI="${ESMINI_HOME:?Set ESMINI_HOME to esmini install directory}/bin/esmini"

# Derive base name from xosc filename
BASENAME="$(basename "$XOSC_FILE" .xosc)"
FRAME_DIR="$(mktemp -d)"
trap 'rm -rf "$FRAME_DIR"' EXIT

mkdir -p "$OUTPUT_DIR"

echo "==> Rendering $BASENAME..."

# Run esmini with borderless viewer window + capture_screen
# --capture_screen writes screen_shot_XXXXX.tga to CWD
# Use --borderless-window to avoid title bar eating pixels
cd "$FRAME_DIR"
"$ESMINI" \
  --osc "$XOSC_FILE" \
  --borderless-window 0 0 1920 1080 \
  --capture_screen \
  --collision \
  --camera_mode flex-orbit \
  --follow_object 0 \
  --fixed_timestep 0.033 \
  --disable_log \
  || { echo "esmini failed for $BASENAME"; exit 1; }

# Count frames
FRAME_COUNT=$(ls "$FRAME_DIR"/screen_shot_*.tga 2>/dev/null | wc -l | tr -d ' ')
if [ "$FRAME_COUNT" -eq 0 ]; then
  echo "No frames captured for $BASENAME"
  exit 1
fi
echo "   Captured $FRAME_COUNT frames"

# Convert TGA sequence to MP4 using ffmpeg
# crop filter ensures even dimensions (required by libx264)
ffmpeg -y -loglevel warning \
  -framerate 30 \
  -i "$FRAME_DIR/screen_shot_%05d.tga" \
  -vf "crop=trunc(iw/2)*2:trunc(ih/2)*2" \
  -c:v libx264 -pix_fmt yuv420p -crf 23 \
  -movflags +faststart \
  "$OUTPUT_DIR/${BASENAME}.mp4"

# Extract thumbnail at 3 seconds into the video
ffmpeg -y -loglevel warning \
  -i "$OUTPUT_DIR/${BASENAME}.mp4" \
  -ss 00:00:03 -frames:v 1 -update 1 \
  -vf "scale=640:360" \
  "$OUTPUT_DIR/${BASENAME}.jpg"

echo "   Output: $OUTPUT_DIR/${BASENAME}.mp4"
echo "   Thumb:  $OUTPUT_DIR/${BASENAME}.jpg"

# Brief delay to let GPU/OpenGL context fully release between renders
sleep 1
