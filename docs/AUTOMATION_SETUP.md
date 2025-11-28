# Automation Setup Guide

This guide explains how to automatically generate follow-up emails after your Fathom meetings.

## What's New

✅ **Automatic Participant Email Extraction**
- The script now automatically extracts external participant emails from Fathom
- External participants (non-@crono.one) are automatically added to the "To:" field
- You can still manually specify recipients with `--to` if needed

## Automation Options

### Option 1: Run After Each Meeting (Manual Trigger)

Simply run this command after your meeting:
```bash
cd /Users/lorenzo/cazzeggio
python3 meeting_followup.py --model claude
```

The script will:
1. Fetch your latest meeting from Fathom
2. Extract external participant emails automatically
3. Generate a follow-up email with Claude
4. Create a Gmail draft ready to review and send

### Option 2: Scheduled Automation (Cron Job)

Run automatically at specific times (e.g., every hour during work hours):

#### Step 1: Edit your crontab
```bash
crontab -e
```

#### Step 2: Add one of these schedules

**Every hour from 9 AM to 6 PM on weekdays:**
```cron
0 9-18 * * 1-5 /Users/lorenzo/cazzeggio/auto_followup.sh
```

**Every 30 minutes from 9 AM to 6 PM on weekdays:**
```cron
*/30 9-18 * * 1-5 /Users/lorenzo/cazzeggio/auto_followup.sh
```

**At 1 PM and 6 PM every weekday (twice daily):**
```cron
0 13,18 * * 1-5 /Users/lorenzo/cazzeggio/auto_followup.sh
```

**Right after lunch at 2 PM every weekday:**
```cron
0 14 * * 1-5 /Users/lorenzo/cazzeggio/auto_followup.sh
```

#### Step 3: Save and exit
- In vim: Press `ESC`, then type `:wq` and press Enter
- In nano: Press `Ctrl+X`, then `Y`, then Enter

#### Step 4: Verify cron is running
```bash
crontab -l
```

### Option 3: Fathom Webhooks (Advanced - Future Enhancement)

Fathom doesn't currently support webhooks, but you can check their API for updates:
- https://developers.fathom.ai/

If webhooks become available, you could set up a server to receive notifications when recordings complete.

## How It Works Now

### Automatic Email Extraction

The script automatically:
1. Fetches the latest meeting from Fathom
2. Extracts all `calendar_invitees` from the meeting
3. Filters for `is_external: true` (non-Crono team members)
4. Uses those emails as recipients in the Gmail draft

Example output:
```
📥 Fetching meeting transcript from Fathom...
✓ Found meeting: Crono | Demo with Agatha Grégoire
✓ Found 1 external participant(s): agatha@soldeibiza.com
```

### Manual Override

You can still manually specify recipients:
```bash
# Single recipient
python3 meeting_followup.py --model claude --to agatha@example.com

# Multiple recipients
python3 meeting_followup.py --model claude --to agatha@example.com john@example.com
```

## Checking Automation Logs

View the automation log to see when drafts were created:
```bash
tail -f /Users/lorenzo/cazzeggio/auto_followup.log
```

## Preventing Duplicate Drafts

The current setup creates a draft for every run. To prevent duplicates:

### Option A: Check Manually
- Review your Gmail drafts before running again
- Delete or send the existing draft first

### Option B: Smart Detection (Future Enhancement)
We could add logic to:
- Track which meetings have already been processed
- Skip meetings that already have drafts
- Only process new meetings since last run

Would you like me to implement duplicate detection?

## Troubleshooting

### "No meetings found"
- Make sure you had a recent meeting recorded in Fathom
- Check that your Fathom API key is valid

### "No external participants found"
- This happens when all participants are @crono.one
- Use `--to` to manually specify recipients

### Cron job not running
```bash
# Check if cron is running on macOS
sudo launchctl list | grep cron

# View system logs for cron
log show --predicate 'process == "cron"' --last 1h
```

### Gmail authentication expired
```bash
# Delete the token and re-authenticate
rm /Users/lorenzo/cazzeggio/token.json
python3 meeting_followup.py --model claude
```

## Best Practices

1. **Check drafts before sending** - Always review AI-generated emails
2. **Run after meetings end** - Wait 5-10 minutes for Fathom to process the transcript
3. **Monitor the log file** - Check for errors regularly
4. **Keep credentials secure** - Never commit `.env`, `credentials.json`, or `token.json` to git

## Next Steps

Some ideas to enhance automation:
- Add duplicate detection (track processed meetings)
- Support for Gemini model in cron
- Slack/Discord notifications when draft is created
- Integration with your CRM
- Custom email templates per meeting type

Let me know which enhancements you'd like!
