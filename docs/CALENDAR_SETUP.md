# Google Calendar Setup Guide

## New Feature: Automatic Follow-up Meeting Creation

The script now automatically creates follow-up calendar events with these features:

✅ **AI-powered date extraction** - Analyzes transcript for mentioned follow-up dates
✅ **Smart defaults** - If no date mentioned, schedules for same time next week
✅ **Auto-add participants** - Includes all external meeting participants
✅ **Google Meet link** - Automatically creates a Meet link for the follow-up
✅ **Email invitations** - Sends calendar invites to all participants

## Setup Steps

### 1. Enable Google Calendar API

1. Go to https://console.cloud.google.com/
2. Select your project (the same one you used for Gmail)
3. Go to **"APIs & Services"** → **"Library"**
4. Search for **"Google Calendar API"**
5. Click **"Enable"**

### 2. Update OAuth Consent Screen (if needed)

1. Go to **"APIs & Services"** → **"OAuth consent screen"**
2. Scroll to **"Scopes"** section
3. Click **"Add or Remove Scopes"**
4. Search for and add:
   - `https://www.googleapis.com/auth/calendar` (Manage calendars)
5. Click **"Update"** and **"Save and Continue"**

### 3. Re-authenticate

Since we're adding a new scope (Calendar), you need to re-authenticate:

```bash
# Delete the existing token
rm /Users/lorenzo/cazzeggio/token.json

# Run the script - it will ask you to authenticate again
python3 meeting_followup.py --model claude
```

When the browser opens:
1. Sign in with **lorenzo@crono.one**
2. You'll see permissions for both **Gmail** and **Calendar**
3. Click **"Allow"** to grant access

## How It Works

### AI Date Extraction

The script analyzes the meeting transcript looking for phrases like:
- "Let's schedule a follow-up next Tuesday at 2 PM"
- "Can we meet again on the 25th?"
- "Let's reconnect in two weeks"
- "How about Thursday afternoon?"

### Smart Defaults

If no specific date is mentioned, the script:
- Schedules the follow-up for **same time next week**
- Uses the **same duration** (30 minutes)
- Includes **all external participants** from the original meeting

### Example Output

```
📅 Creating follow-up meeting...
✅ Follow-up meeting created!
   Date: 2025-11-25 14:00 UTC
   Attendees: alex@example.com, laura@example.com
   📌 Date extracted from transcript: 'next Tuesday at 2 PM'

   View in Google Calendar:
   https://calendar.google.com/
```

## Testing

Test the calendar integration independently:

```bash
cd /Users/lorenzo/cazzeggio/modules
python3 calendar_event_creator.py
```

This will create a test event 1 week from now.

## Troubleshooting

### "Insufficient Permission" Error

You need to re-authenticate with Calendar permissions:
```bash
rm /Users/lorenzo/cazzeggio/token.json
python3 meeting_followup.py --model claude
```

### Calendar API Not Enabled

Enable it in Google Cloud Console:
https://console.cloud.google.com/apis/library/calendar-json.googleapis.com

### Wrong Timezone

The script uses the timezone from your original meeting. If times are wrong, check:
- Your Fathom settings
- Your Google Calendar default timezone

## Customization

### Change Meeting Duration

Edit `/Users/lorenzo/cazzeggio/meeting_followup.py` line 244:
```python
duration_minutes=30,  # Change to 60 for 1-hour meetings
```

### Disable Calendar Event Creation

If you don't want calendar events created, comment out the calendar creation section (lines 215-264).

### Custom Meeting Descriptions

Edit line 246 in `meeting_followup.py`:
```python
description=f"Follow-up from meeting on {original_meeting_time}\n\nYour custom text here"
```

## Privacy & Security

- Calendar events are created in **your** Google Calendar (lorenzo@crono.one)
- Invitations are sent to participants automatically
- The script uses OAuth 2.0 - your credentials never leave your machine
- All calendar events include a Google Meet link

## What Gets Created

Each follow-up meeting includes:
- **Title**: "Follow-up: [Original Meeting Title]"
- **Date/Time**: Extracted from transcript or +1 week
- **Duration**: 30 minutes (configurable)
- **Attendees**: All external participants
- **Google Meet link**: Auto-generated
- **Reminders**:
  - Email: 1 day before
  - Popup: 30 minutes before

Enjoy your fully automated follow-up workflow! 🎉
