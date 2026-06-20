#!/usr/bin/env bash
# Regenerate all app icons from the single SVG source (frontend/public/icon.svg):
# the PWA raster PNGs and the macOS .icns for the .app bundle.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$ROOT/frontend/public/icon.svg"

[ -f "$SRC" ] || { echo "missing icon source: $SRC"; exit 1; }
command -v rsvg-convert >/dev/null 2>&1 || {
  echo "rsvg-convert required — install with: brew install librsvg"; exit 1; }

# PWA raster icons (served by the console)
rsvg-convert -w 192 -h 192 "$SRC" -o "$ROOT/frontend/public/icon-192.png"
rsvg-convert -w 512 -h 512 "$SRC" -o "$ROOT/frontend/public/icon-512.png"
rsvg-convert -w 180 -h 180 "$SRC" -o "$ROOT/frontend/public/apple-touch-icon.png"
echo "wrote PWA icons -> frontend/public/icon-192.png, icon-512.png, apple-touch-icon.png"

# macOS .icns for the .app bundle
BUILD="$ROOT/build"
ICONSET="$BUILD/AppIcon.iconset"
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  rsvg-convert -w "$s"          -h "$s"          "$SRC" -o "$ICONSET/icon_${s}x${s}.png"
  rsvg-convert -w "$((s * 2))"  -h "$((s * 2))"  "$SRC" -o "$ICONSET/icon_${s}x${s}@2x.png"
done
if command -v iconutil >/dev/null 2>&1; then
  iconutil -c icns "$ICONSET" -o "$BUILD/AppIcon.icns"
  echo "wrote $BUILD/AppIcon.icns"
else
  echo "iconutil not found (non-macOS) — skipped .icns; PWA PNGs still written."
fi
