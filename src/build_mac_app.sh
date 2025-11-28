#!/bin/bash
# Build and install Mac menu bar app

echo "🚀 Building Crono Follow-up Mac App"
echo "===================================="
echo ""

# Check if py2app is installed
if ! python3 -c "import py2app" 2>/dev/null; then
    echo "📦 Installing py2app..."
    pip3 install py2app
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build dist

# Build the app
echo "🔨 Building app..."
python3 setup_mac_app.py py2app

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "📱 App location: dist/menu_bar_app.app"
    echo ""
    echo "To install:"
    echo "1. Open Finder"
    echo "2. Navigate to: $(pwd)/dist"
    echo "3. Drag 'menu_bar_app.app' to your Applications folder"
    echo "4. Open it from Applications (or Spotlight search 'Crono')"
    echo ""
    echo "To auto-start on login:"
    echo "1. Open System Preferences → Users & Groups"
    echo "2. Click 'Login Items'"
    echo "3. Click '+' and add 'menu_bar_app.app'"
    echo ""
else
    echo ""
    echo "❌ Build failed. Check errors above."
    exit 1
fi
