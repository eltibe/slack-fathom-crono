# 🚀 Simple Mac App Install (No Build Required!)

## ✨ New Interface

**One dialog for everything:**
```
Format: number:actions

Examples:
  1:ec   → Meeting 1: Email + Calendar
  2:e    → Meeting 2: Email only
  3:ecn  → Meeting 3: Email + Calendar + Note

e = Email (always created)
c = Calendar event
n = Crono note extraction
```

---

## 🎯 Option 1: Run Directly (Easiest)

### Start the App
```bash
cd /Users/lorenzo/cazzeggio
./launch_app.sh
```

Keep the terminal open! You'll see the 🚀 icon in your menu bar.

---

## 🍎 Option 2: Create Mac App with Automator

### Step 1: Open Automator
1. Press `Cmd + Space`
2. Type "Automator"
3. Press Enter

### Step 2: Create Application
1. Click "New Document"
2. Choose "Application"
3. Click "Choose"

### Step 3: Add Shell Script
1. In the left sidebar, search for "Run Shell Script"
2. Drag "Run Shell Script" to the right panel
3. Paste this script:
   ```bash
   cd /Users/lorenzo/cazzeggio
   /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 menu_bar_app.py
   ```

### Step 4: Save
1. Press `Cmd + S`
2. Name it: "Crono Follow-up"
3. Save to: **Desktop** (or Applications)
4. Click "Save"

### Step 5: Run It!
1. Double-click "Crono Follow-up.app" on your Desktop
2. Look for 🚀 icon in menu bar!

---

## 🔄 Auto-Start on Login

### Method 1: Login Items (Recommended)
1. Open **System Preferences**
2. Go to **Users & Groups**
3. Click **Login Items** tab
4. Click **+** button
5. Select **Crono Follow-up.app** from Desktop
6. Click **Add**

Now it starts automatically when you log in!

### Method 2: LaunchAgent
Create: `~/Library/LaunchAgents/com.crono.followup.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.crono.followup</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/lorenzo/cazzeggio/launch_app.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/crono-followup.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/crono-followup-error.log</string>
</dict>
</plist>
```

Then:
```bash
launchctl load ~/Library/LaunchAgents/com.crono.followup.plist
```

---

## 🎯 How to Use

### Daily Workflow

1. **Click 🚀** in menu bar
2. **Select "📧 Generate Follow-up Email"**
3. **Enter:** `1:ec` (or your choice)
4. **Confirm**
5. **Done!** ✅

### Format Guide

| Input | Email | Calendar | Note | Use Case |
|-------|-------|----------|------|----------|
| `1:e` | ✅ | ❌ | ❌ | Quick email only |
| `1:c` | ✅ | ✅ | ❌ | Email + follow-up event |
| `1:n` | ✅ | ❌ | ✅ | Email + extract sales data |
| `1:ec` | ✅ | ✅ | ❌ | Standard follow-up |
| `1:en` | ✅ | ❌ | ✅ | Email + sales notes |
| `1:ecn` | ✅ | ✅ | ✅ | Everything! |

**Remember:** Email is ALWAYS created! 📧

---

## 🐛 Troubleshooting

### Can't see 🚀 icon
- Check if app is running: `ps aux | grep menu_bar_app`
- Look in menu bar (top-right)
- Check hidden icons area (`>>` symbol)

### App doesn't start
Run manually to see errors:
```bash
cd /Users/lorenzo/cazzeggio
python3 menu_bar_app.py
```

### "Permission Denied"
Make sure scripts are executable:
```bash
chmod +x launch_app.sh
```

### No meetings showing
- Check Fathom API key in `.env`
- Make sure you have meetings today
- Click "🔄 Refresh Badge"

---

## 📋 Quick Reference

### Dialog Example
```
1. [14:30] Discovery Call with Acme Corp
2. [16:00] Demo with TechStartup

📧 = Email draft
📅 = Calendar event
📝 = Crono note

Format: number:actions
Examples:
  1:ec   → Meeting 1: Email + Calendar
  2:e    → Meeting 2: Email only
  3:ecn  → Meeting 3: All

Enter your choice: 1:ec
```

### Confirmation
```
Meeting: Discovery Call with Acme Corp

Will create:
📧 Email draft
📅 Calendar event

[Confirm] [Cancel]
```

### Success!
```
Crono Follow-up
✅ Success!
Draft created in Gmail! Calendar event added!
```

---

## 🎉 That's It!

Your app is now installed and ready to use. Just click 🚀 whenever you need to process a meeting! 🚀

For Crono notes: The data is extracted and shown in terminal - copy/paste it into Crono until the API supports creation.
