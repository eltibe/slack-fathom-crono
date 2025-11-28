#!/bin/bash
# Install and Setup Crono Menu Bar App

echo "🚀 Installing Crono Menu Bar App..."
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Install rumps
echo "📦 Installing dependencies..."
pip3 install rumps --quiet

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Make the menu bar app executable
chmod +x menu_bar_app.py

echo ""
echo "✅ Installation complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 HOW TO USE:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1️⃣  START THE APP:"
echo "   python3 menu_bar_app.py"
echo ""
echo "2️⃣  YOU'LL SEE:"
echo "   🚀 icon in your menu bar (top right)"
echo "   Badge with today's meeting count"
echo ""
echo "3️⃣  CLICK THE ICON TO:"
echo "   📧 Generate Follow-up Email"
echo "   📊 View Today's Meetings"
echo "   📅 Open Calendar"
echo "   ✉️  Open Gmail Drafts"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 TIP: Keep it running in the background!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Want to start it now? (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Starting Crono Menu Bar App..."
    echo "   (Press Ctrl+C to stop)"
    echo ""
    python3 menu_bar_app.py
fi
