#!/bin/bash
# Setup Crono Menu Bar App to start automatically on login

echo "🔧 Setting up auto-start for Crono Menu Bar App..."
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create LaunchAgent plist
PLIST_PATH="$HOME/Library/LaunchAgents/com.crono.menubar.plist"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.crono.menubar</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>${SCRIPT_DIR}/menu_bar_app.py</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/menubar.log</string>

    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/menubar_error.log</string>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF

echo "✅ LaunchAgent created at:"
echo "   $PLIST_PATH"
echo ""

# Load the LaunchAgent
launchctl unload "$PLIST_PATH" 2>/dev/null  # Unload if already loaded
launchctl load "$PLIST_PATH"

if [ $? -eq 0 ]; then
    echo "✅ Auto-start enabled!"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 SUCCESS!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "The Crono Menu Bar App will now:"
    echo "  ✅ Start automatically when you log in"
    echo "  ✅ Run in the background"
    echo "  ✅ Show 🚀 icon in your menu bar"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "COMMANDS:"
    echo "  Stop:     launchctl unload $PLIST_PATH"
    echo "  Start:    launchctl load $PLIST_PATH"
    echo "  Disable:  rm $PLIST_PATH"
    echo ""
else
    echo "❌ Failed to load LaunchAgent"
    exit 1
fi
