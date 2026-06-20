#!/usr/bin/env bash
# Build Catch-Up.app — a double-clickable macOS launcher that boots the local
# server (scripts/run.sh) and opens the console in a standalone window.
#
# The repo path is baked into the bundle at build time, so the .app can be moved
# to the Desktop / Applications and still find this clone. Re-run after moving the
# repo. Usage: scripts/make_app.sh [DEST_DIR]   (default: build/)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="${1:-$ROOT/build}"
APP="$DEST/Catch-Up.app"
CON="$APP/Contents"

mkdir -p "$DEST"
[ -f "$ROOT/build/AppIcon.icns" ] || "$SCRIPT_DIR/make_icon.sh"

rm -rf "$APP"
mkdir -p "$CON/MacOS" "$CON/Resources"

# Launcher stub — execs run.sh from THIS clone (path baked in now).
cat > "$CON/MacOS/run" <<EOF
#!/bin/bash
exec "$ROOT/scripts/run.sh"
EOF
chmod +x "$CON/MacOS/run"

cp "$ROOT/build/AppIcon.icns" "$CON/Resources/AppIcon.icns" 2>/dev/null || true

cat > "$CON/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Catch-Up</string>
  <key>CFBundleDisplayName</key><string>Catch-Up</string>
  <key>CFBundleIdentifier</key><string>com.catchup.local</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

echo "Built $APP"
echo "Drag it to your Desktop (or Applications), then double-click to launch."
