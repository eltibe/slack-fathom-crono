# Migration Example: Old to New OAuth Implementation

This document shows how to update existing code from the file-based OAuth to the database-backed OAuth implementation.

## Example 1: Gmail Draft Creation in Slack Handler

### OLD CODE (File-based)

```python
from src.modules.gmail_draft_creator import GmailDraftCreator

@app.route('/slack/interactive', methods=['POST'])
def handle_interactive():
    # ... extract data from Slack interaction ...

    # Old approach - uses files
    gmail = GmailDraftCreator(
        credentials_file='credentials.json',
        token_file='token.json'
    )

    draft_id = gmail.create_draft(
        subject=subject,
        body=body,
        to=[recipient_email]
    )

    return jsonify({"draft_id": draft_id})
```

### NEW CODE (Database-backed)

```python
from src.modules.gmail_draft_creator import GmailDraftCreator
from src.database import get_db
from src.models import User
from src.models.tenant import Tenant

@app.route('/slack/interactive', methods=['POST'])
def handle_interactive():
    # ... extract data from Slack interaction ...
    slack_user_id = body['user']['id']
    team_id = body['team']['id']

    with get_db() as db:
        # Find tenant and user
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404

        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        # Check if user has connected Google account
        if not user or not user.settings or not user.settings.gmail_token:
            return jsonify({
                "text": "Please connect your Google account first:",
                "attachments": [{
                    "text": "Visit /settings to connect your Google account"
                }]
            }), 200

        # Define callback to save refreshed tokens
        def save_gmail_token(new_token_json):
            user.settings.gmail_token = new_token_json
            db.commit()
            logger.info(f"Refreshed Gmail token for user {slack_user_id}")

        # New approach - uses database tokens
        try:
            gmail = GmailDraftCreator(
                token_json=user.settings.gmail_token,
                token_save_callback=save_gmail_token
            )

            draft_id = gmail.create_draft(
                subject=subject,
                body=body,
                to=[recipient_email]
            )

            return jsonify({"draft_id": draft_id})

        except ValueError as e:
            logger.error(f"Invalid Gmail token: {e}")
            return jsonify({
                "error": "Your Google connection is invalid. Please reconnect at /settings"
            }), 400
        except Exception as e:
            logger.error(f"Failed to create Gmail draft: {e}")
            return jsonify({"error": "Failed to create draft"}), 500
```

## Example 2: Calendar Event Creation

### OLD CODE

```python
from src.modules.calendar_event_creator import CalendarEventCreator
from datetime import datetime, timedelta
import pytz

def create_followup_event(meeting_data):
    # Old approach
    calendar = CalendarEventCreator(
        credentials_file='credentials.json',
        token_file='token.json'
    )

    meeting_time = datetime.now(pytz.UTC) + timedelta(weeks=1)

    event_id = calendar.create_followup_meeting(
        title="Follow-up Meeting",
        start_datetime=meeting_time,
        duration_minutes=30,
        attendees=meeting_data['attendees']
    )

    return event_id
```

### NEW CODE

```python
from src.modules.calendar_event_creator import CalendarEventCreator
from src.database import get_db
from src.models import User
from src.models.tenant import Tenant
from datetime import datetime, timedelta
import pytz

def create_followup_event(slack_user_id, team_id, meeting_data):
    """
    Create a follow-up calendar event for a user.

    Args:
        slack_user_id: User's Slack ID
        team_id: Slack workspace ID
        meeting_data: Dictionary with meeting details

    Returns:
        event_id: Google Calendar event ID

    Raises:
        ValueError: If user hasn't connected Google account
        Exception: If event creation fails
    """
    with get_db() as db:
        # Find tenant and user
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            raise ValueError("Tenant not found")

        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        # Check if user has connected Google account
        if not user or not user.settings or not user.settings.calendar_token:
            raise ValueError(
                "User has not connected Google account. "
                "Please visit /settings to connect."
            )

        # Define callback to save refreshed tokens
        def save_calendar_token(new_token_json):
            user.settings.calendar_token = new_token_json
            db.commit()
            logger.info(f"Refreshed Calendar token for user {slack_user_id}")

        # New approach - uses database tokens
        calendar = CalendarEventCreator(
            token_json=user.settings.calendar_token,
            token_save_callback=save_calendar_token
        )

        meeting_time = datetime.now(pytz.UTC) + timedelta(weeks=1)

        event_id = calendar.create_followup_meeting(
            title="Follow-up Meeting",
            start_datetime=meeting_time,
            duration_minutes=30,
            attendees=meeting_data['attendees'],
            description=meeting_data.get('description', '')
        )

        return event_id
```

## Example 3: Handling Both Gmail and Calendar Together

### OLD CODE

```python
def handle_meeting_followup(meeting_data):
    # Create email draft
    gmail = GmailDraftCreator()
    draft_id = gmail.create_draft(...)

    # Create calendar event
    calendar = CalendarEventCreator()
    event_id = calendar.create_followup_meeting(...)

    return {
        "draft_id": draft_id,
        "event_id": event_id
    }
```

### NEW CODE

```python
def handle_meeting_followup(slack_user_id, team_id, meeting_data):
    """
    Create both email draft and calendar event for meeting follow-up.

    Returns:
        dict: Contains draft_id and event_id

    Raises:
        ValueError: If user hasn't connected Google account
    """
    with get_db() as db:
        # Get user and settings
        tenant = db.query(Tenant).filter(Tenant.slack_team_id == team_id).first()
        if not tenant:
            raise ValueError("Tenant not found")

        user = db.query(User).filter(
            User.slack_user_id == slack_user_id,
            User.tenant_id == tenant.id
        ).first()

        # Check if user has connected Google account
        if not user or not user.settings:
            raise ValueError("User settings not found")

        if not user.settings.gmail_token or not user.settings.calendar_token:
            raise ValueError(
                "Please connect your Google account at /settings to use this feature"
            )

        # Define callbacks for token refresh
        def save_gmail_token(new_token_json):
            user.settings.gmail_token = new_token_json
            db.commit()

        def save_calendar_token(new_token_json):
            user.settings.calendar_token = new_token_json
            db.commit()

        # Create Gmail client
        gmail = GmailDraftCreator(
            token_json=user.settings.gmail_token,
            token_save_callback=save_gmail_token
        )

        # Create Calendar client
        calendar = CalendarEventCreator(
            token_json=user.settings.calendar_token,
            token_save_callback=save_calendar_token
        )

        # Create draft
        draft_id = gmail.create_draft(
            subject=meeting_data['subject'],
            body=meeting_data['body'],
            to=meeting_data['recipients']
        )

        # Create event
        event_id = calendar.create_followup_meeting(
            title=meeting_data['title'],
            start_datetime=meeting_data['datetime'],
            duration_minutes=30,
            attendees=meeting_data['attendees']
        )

        return {
            "draft_id": draft_id,
            "event_id": event_id
        }
```

## Key Changes Summary

### 1. Import Changes
**No changes needed** - same imports work for both versions

### 2. Initialization Changes

**OLD:**
```python
gmail = GmailDraftCreator()  # or with file paths
```

**NEW:**
```python
gmail = GmailDraftCreator(token_json, save_callback)
```

### 3. Database Context Required

**NEW CODE ALWAYS NEEDS:**
```python
from src.database import get_db
from src.models import User
from src.models.tenant import Tenant

with get_db() as db:
    # Query user settings
    # Create clients
    # Use clients
```

### 4. Error Handling

**NEW CODE SHOULD CHECK:**
```python
# Check if user exists
if not user:
    raise ValueError("User not found")

# Check if settings exist
if not user.settings:
    raise ValueError("User settings not found")

# Check if Google account connected
if not user.settings.gmail_token:
    raise ValueError("Google account not connected")
```

### 5. Token Refresh Callbacks

**ALWAYS PROVIDE CALLBACK:**
```python
def save_token(new_token_json):
    user.settings.gmail_token = new_token_json
    db.commit()

gmail = GmailDraftCreator(token_json, save_token)
```

## Testing Checklist

After migrating code:

- [ ] Remove `credentials.json` and `token.json` references
- [ ] Add database queries for user/tenant
- [ ] Add Google account connection checks
- [ ] Add token save callbacks
- [ ] Add error handling for missing tokens
- [ ] Test with connected user
- [ ] Test with disconnected user
- [ ] Test token refresh (wait for expiry or force)
- [ ] Verify tokens are saved to database after refresh
- [ ] Check logs for authentication errors

## Common Pitfalls

### Pitfall 1: Forgetting Database Context
```python
# WRONG - no database context
gmail = GmailDraftCreator(user.settings.gmail_token, save_callback)

# RIGHT - within database context
with get_db() as db:
    user = db.query(User).filter(...).first()
    gmail = GmailDraftCreator(user.settings.gmail_token, save_callback)
```

### Pitfall 2: No Token Save Callback
```python
# WORKS BUT NOT IDEAL - tokens won't be refreshed in DB
gmail = GmailDraftCreator(token_json)

# BETTER - tokens will be saved after refresh
gmail = GmailDraftCreator(token_json, save_callback)
```

### Pitfall 3: Not Checking if Google Connected
```python
# BAD - will crash if user hasn't connected
gmail = GmailDraftCreator(user.settings.gmail_token, save_callback)

# GOOD - check first
if not user.settings.gmail_token:
    return jsonify({"error": "Please connect Google account"}), 400
gmail = GmailDraftCreator(user.settings.gmail_token, save_callback)
```

### Pitfall 4: Wrong Token for Service
```python
# WRONG - using calendar token for Gmail
gmail = GmailDraftCreator(user.settings.calendar_token, save_callback)

# RIGHT - use gmail_token for Gmail
gmail = GmailDraftCreator(user.settings.gmail_token, save_callback)

# NOTE: Usually both tokens are the same (same OAuth session)
# but always use the correct one for clarity
```

## Need Help?

- See full documentation: `GOOGLE_OAUTH_SETUP.md`
- Quick reference: `GOOGLE_OAUTH_QUICK_START.md`
- Check existing routes in `src/slack_webhook_handler.py` for examples
- Look at test code in `src/modules/gmail_draft_creator.py`
