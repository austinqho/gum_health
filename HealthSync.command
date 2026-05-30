#!/bin/bash
# HealthSync installer
# Double-click this file on a Mac to install the watcher.

set -e

INSTALL_DIR="$HOME/Library/Application Support/HealthSync"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/com.healthsync.watcher.plist"

echo "→ Installing HealthSync watcher..."

mkdir -p "$INSTALL_DIR" "$LAUNCH_AGENTS_DIR"

# Locate src folder
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR/src"

if [ ! -d "$SRC_DIR" ]; then
  echo "✗ Could not find src/ folder next to this installer."
  echo "  Make sure you extracted the full HealthSync folder before running."
  exit 1
fi

rm -rf "$INSTALL_DIR/health_observer"
ditto "$SRC_DIR/health_observer" "$INSTALL_DIR/health_observer"
find "$INSTALL_DIR/health_observer" -name "__pycache__" -type d -prune -exec rm -rf {} +

# Find a system python3 to bootstrap the venv
SYSTEM_PYTHON3="$(command -v python3 || true)"
if [ -z "$SYSTEM_PYTHON3" ]; then
  echo "✗ python3 not found. Install Python 3 from python.org and re-run."
  exit 1
fi

# Create an isolated venv inside the install folder so the background
# service always uses the same Python with the right libraries installed,
# regardless of what else is on this Mac.
VENV_DIR="$INSTALL_DIR/venv"
PYTHON3="$VENV_DIR/bin/python3"

if [ ! -x "$PYTHON3" ]; then
  echo "→ Creating isolated Python environment..."
  "$SYSTEM_PYTHON3" -m venv "$VENV_DIR" || {
    echo "✗ Could not create venv. You may need to install the Python venv module."
    exit 1
  }
fi

# Install Python deps into the venv
echo "→ Installing Python dependencies (watchdog, certifi)..."
"$PYTHON3" -m pip install --quiet --upgrade pip
"$PYTHON3" -m pip install --quiet watchdog certifi || {
  echo "  pip install failed inside the venv."
  exit 1
}

# Build LaunchAgent
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.healthsync.watcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON3</string>
    <string>-m</string>
    <string>health_observer.runtime.mac</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$INSTALL_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>$INSTALL_DIR/watcher.log</string>
  <key>StandardErrorPath</key>
  <string>$INSTALL_DIR/watcher.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ""
echo "✓ HealthSync watcher installed and running."
echo ""
echo "  Outputs: $HOME/Desktop/HealthSync/"
echo "  Logs:    $INSTALL_DIR/watcher.log"
echo ""
echo "  To uninstall:"
echo "    launchctl unload \"$PLIST_PATH\""
echo "    rm \"$PLIST_PATH\""
echo "    rm -rf \"$INSTALL_DIR\""
echo ""
read -p "Press return to close..." || true
