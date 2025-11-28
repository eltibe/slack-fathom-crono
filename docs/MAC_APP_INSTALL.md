# 🍎 Mac App Installation Guide

## 📱 New Interface Design

The app now has a **single dialog** where you can choose:
- **Which meeting** to process
- **Which actions** to take (Email, Calendar, Note)

### Quick Format

Enter: `number:actions`

**Actions:**
- `e` = Email draft (always recommended)
- `c` = Calendar event
- `n` = Crono note extraction

### Examples

```
1:ec   → Meeting 1: Email + Calendar
2:e    → Meeting 2: Email only
3:ecn  → Meeting 3: Email + Calendar + Note
1:en   → Meeting 1: Email + Note only
```

**Note:** Email is always created! The format just makes it explicit.

---

## 🚀 Build & Install

### Step 1: Build the App

```bash
cd /Users/lorenzo/cazzeggio
./build_mac_app.sh
```

This will:
- Install py2app if needed
- Build a standalone Mac app
- Create `dist/menu_bar_app.app`

### Step 2: Install the App

**Option A: Drag to Applications**
1. Open Finder
2. Navigate to `/Users/lorenzo/cazzeggio/dist`
3. Drag `menu_bar_app.app` to Applications folder
4. Open from Applications or Spotlight

**Option B: Use from dist folder**
```bash
open dist/menu_bar_app.app
```

### Step 3: First Run

The first time you run it:
1. You'll see 🚀 icon in menu bar
2. Click it to test!

---

## 🎯 How to Use

### Daily Workflow

1. **Click 🚀** in menu bar
2. **Select "📧 Generate Follow-up Email"**
3. **Enter format:** `1:ec` (meeting 1, email + calendar)
4. **Confirm** the actions
5. **Wait for notification** ✅
6. **Check Gmail** for draft
7. **Check Calendar** for event (if selected)
8. **Check Terminal** for Crono note data (if selected)

### Meeting Selection Examples

**Scenario 1: Just want email**
```
Input: 1:e
Creates: Email draft only
```

**Scenario 2: Email + Calendar**
```
Input: 1:ec
Creates: Email draft + Calendar event
```

**Scenario 3: Everything**
```
Input: 1:ecn
Creates: Email + Calendar + Extracts Crono note data
```

**Scenario 4: Email + Note (no calendar)**
```
Input: 1:en
Creates: Email + Extracts Crono note data
```

---

## ⚙️ Auto-Start on Login

### Option 1: System Preferences
1. Open **System Preferences**
2. Go to **Users & Groups**
3. Click **Login Items** tab
4. Click **+** button
5. Navigate to Applications
6. Select **menu_bar_app.app**
7. Click **Add**

### Option 2: LaunchAgent (Advanced)
See the original documentation for creating a plist file.

---

## 🎨 What Gets Created

| Format | Email | Calendar | Crono Note |
|--------|-------|----------|------------|
| `1:e` | ✅ | ❌ | ❌ |
| `1:c` | ✅ | ✅ | ❌ |
| `1:n` | ✅ | ❌ | ✅ |
| `1:ec` | ✅ | ✅ | ❌ |
| `1:en` | ✅ | ❌ | ✅ |
| `1:cn` | ✅ | ✅ | ✅ |
| `1:ecn` | ✅ | ✅ | ✅ |

**Note:** Email is ALWAYS created because that's the primary purpose!

---

## 🐛 Troubleshooting

### App doesn't appear in menu bar

**Check if app is running:**
```bash
ps aux | grep menu_bar_app
```

**Try running from terminal to see errors:**
```bash
/Users/lorenzo/cazzeggio/dist/menu_bar_app.app/Contents/MacOS/menu_bar_app
```

### "App is damaged" error

macOS Gatekeeper might block it. To fix:
```bash
xattr -cr /Users/lorenzo/cazzeggio/dist/menu_bar_app.app
```

Then try opening again.

### Missing .env file

The app needs your `.env` file with API keys. Make sure it's in:
```
/Users/lorenzo/cazzeggio/.env
```

Or if installed in Applications, copy it to:
```
~/Library/Application Support/Crono Follow-up/.env
```

### App crashes on startup

Run from terminal to see error:
```bash
/Users/lorenzo/cazzeggio/dist/menu_bar_app.app/Contents/MacOS/menu_bar_app
```

Check for:
- Missing API keys in `.env`
- Network connection issues
- Python module errors

---

## 📋 Quick Reference

### Dialog Format
```
Meeting List:
1. [14:30] Discovery Call with Acme
2. [16:00] Demo with TechStartup

📧 = Email draft
📅 = Calendar event
📝 = Crono note

Format: number:actions
Enter: 1:ec
```

### Confirmation Dialog
```
Meeting: Discovery Call with Acme

Will create:
📧 Email draft
📅 Calendar event

[Confirm] [Cancel]
```

### Success Notification
```
Crono Follow-up
✅ Success!
Draft created in Gmail! Calendar event added!
```

---

## 🔄 Updating the App

When you make changes to the code:

1. **Rebuild:**
   ```bash
   ./build_mac_app.sh
   ```

2. **Quit old app:**
   - Click 🚀 → Quit Crono

3. **Reopen new version:**
   ```bash
   open dist/menu_bar_app.app
   ```

---

## 📞 Support

If you encounter issues:
1. Check terminal output for errors
2. Verify `.env` file has all API keys
3. Test with `python3 menu_bar_app.py` first
4. Check permissions in System Preferences

---

**Built with:** Python, rumps, Claude AI, Google Gemini, Fathom API, Gmail API, Google Calendar API, Crono API 🚀
