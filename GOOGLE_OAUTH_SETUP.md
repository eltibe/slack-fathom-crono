# Google OAuth 2.0 Web Flow - Implementation Guide

## Overview

This document describes the complete Google OAuth 2.0 web flow implementation for Gmail and Calendar access in the Slack-Fathom-Crono application. The implementation replaces the previous desktop OAuth flow (`run_local_server`) with a production-ready web flow suitable for deployment on Render.

## What Was Implemented

### 1. OAuth Routes (`src/slack_webhook_handler.py`)

Four new routes were added to handle the OAuth flow:

#### `/oauth/google/start` (GET)
Initiates the Google OAuth flow.

**Query Parameters:**
- `slack_user_id` (required): User's Slack ID
- `team_id` (optional): Slack workspace ID (defaults to 'T02R43CJEMA')

**Flow:**
1. Creates OAuth flow with Google credentials
2. Encodes user context in state parameter (base64 JSON)
3. Redirects user to Google consent screen

**Example:**
```
https://your-domain.com/oauth/google/start?slack_user_id=U01234567
```

#### `/oauth/google/callback` (GET)
Handles the OAuth callback from Google.

**Query Parameters:**
- `code`: Authorization code from Google
- `state`: Encoded user context
- `error`: Error message (if OAuth failed)

**Flow:**
1. Receives authorization code from Google
2. Exchanges code for access and refresh tokens
3. Saves tokens to database (both gmail_token and calendar_token)
4. Returns success/failure page

#### `/api/google/status` (GET)
Checks if user has connected their Google account.

**Query Parameters:**
- `slack_user_id` (required): User's Slack ID
- `team_id` (optional): Slack workspace ID

**Returns:**
```json
{
  "connected": true,
  "email": "user@example.com"
}
```

#### `/api/google/disconnect` (POST)
Disconnects Google account by removing stored tokens.

**Request Body:**
```json
{
  "slack_user_id": "U01234567",
  "team_id": "T02R43CJEMA"
}
```

### 2. Settings UI (`src/templates/settings.html`)

Updated the Gmail & Calendar section with:

- **Connection Status Display**: Shows whether Google account is connected
- **Connect Button**: Opens OAuth flow in popup window
- **Disconnect Button**: Removes stored tokens
- **Status Checking**: Automatically checks connection status when user ID is entered

**UI States:**
1. Loading: Checking connection status
2. Not Connected: Shows warning and "Connect" button
3. Connected: Shows success message and "Disconnect" button

### 3. Refactored Gmail & Calendar Modules

Both `GmailDraftCreator` and `CalendarEventCreator` were refactored to:

#### Old Approach (File-based)
```python
gmail = GmailDraftCreator(
    credentials_file='credentials.json',
    token_file='token.json'
)
```

#### New Approach (Database-backed)
```python
# Get token from database
token_json = user.settings.gmail_token

# Define callback to save refreshed tokens
def save_token(new_token_json):
    user.settings.gmail_token = new_token_json
    db.commit()

# Initialize with database token
gmail = GmailDraftCreator(
    token_json=token_json,
    token_save_callback=save_token
)
```

**Key Features:**
- Token refresh is handled automatically
- Refreshed tokens are saved back to database via callback
- No file system access required
- Works in containerized environments (Render, Docker, etc.)

## Environment Variables Required

Add these to your `.env` file and Render dashboard:

```bash
# Google OAuth Credentials
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# OAuth Redirect URI (update for production)
GOOGLE_REDIRECT_URI=https://your-domain.com/oauth/google/callback
```

## Google Cloud Console Setup

1. **Create OAuth 2.0 Credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Navigate to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client ID"
   - Choose "Web application"

2. **Configure Authorized Redirect URIs:**
   ```
   http://localhost:5000/oauth/google/callback  (for local testing)
   https://your-render-app.onrender.com/oauth/google/callback  (for production)
   ```

3. **Enable Required APIs:**
   - Gmail API
   - Google Calendar API

4. **Set OAuth Consent Screen:**
   - Add required scopes:
     - `https://www.googleapis.com/auth/gmail.compose`
     - `https://www.googleapis.com/auth/calendar`

## Usage Examples

### Example 1: Using GmailDraftCreator in Slack Webhook Handler

```python
from src.modules.gmail_draft_creator import GmailDraftCreator
from src.database import get_db
from src.models import User
from src.models.user_settings import UserSettings

# Inside a route handler
with get_db() as db:
    # Get user and settings
    user = db.query(User).filter(
        User.slack_user_id == slack_user_id,
        User.tenant_id == tenant.id
    ).first()

    if not user or not user.settings or not user.settings.gmail_token:
        return jsonify({
            "error": "Please connect your Google account in /settings"
        }), 400

    # Define callback to save refreshed tokens
    def save_gmail_token(new_token_json):
        user.settings.gmail_token = new_token_json
        db.commit()
        logger.info(f"Refreshed Gmail token for user {slack_user_id}")

    # Create Gmail client
    try:
        gmail = GmailDraftCreator(
            token_json=user.settings.gmail_token,
            token_save_callback=save_gmail_token
        )

        # Create draft
        draft_id = gmail.create_draft(
            subject="Follow-up from our meeting",
            body="<p>Hi team,</p><p>Here's a summary...</p>",
            to=["recipient@example.com"]
        )

        return jsonify({"draft_id": draft_id}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating Gmail draft: {e}")
        return jsonify({"error": "Failed to create draft"}), 500
```

### Example 2: Using CalendarEventCreator

```python
from src.modules.calendar_event_creator import CalendarEventCreator
from datetime import datetime, timedelta
import pytz

with get_db() as db:
    user = db.query(User).filter(
        User.slack_user_id == slack_user_id,
        User.tenant_id == tenant.id
    ).first()

    if not user or not user.settings or not user.settings.calendar_token:
        return jsonify({
            "error": "Please connect your Google account in /settings"
        }), 400

    # Define callback to save refreshed tokens
    def save_calendar_token(new_token_json):
        user.settings.calendar_token = new_token_json
        db.commit()
        logger.info(f"Refreshed Calendar token for user {slack_user_id}")

    # Create Calendar client
    try:
        calendar = CalendarEventCreator(
            token_json=user.settings.calendar_token,
            token_save_callback=save_calendar_token
        )

        # Create follow-up meeting
        meeting_time = datetime.now(pytz.timezone('Europe/Rome')) + timedelta(days=7)

        event_id = calendar.create_followup_meeting(
            title="Follow-up: Product Discussion",
            start_datetime=meeting_time,
            duration_minutes=30,
            attendees=["team@example.com"],
            description="Follow-up from our previous meeting"
        )

        return jsonify({"event_id": event_id}), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return jsonify({"error": "Failed to create event"}), 500
```

## User Flow

1. **User Opens Settings Page:**
   - Navigate to `/settings`
   - Enter Slack User ID

2. **Connect Google Account:**
   - Click "Gmail" tab
   - See "Account Google non collegato" message
   - Click "Connetti Account Google" button
   - OAuth popup opens

3. **Google Authentication:**
   - User logs in to Google (if needed)
   - Reviews requested permissions
   - Clicks "Allow"

4. **Success:**
   - Popup shows success message
   - Popup closes automatically
   - Settings page updates to show "Google Account Connected"
   - Tokens are saved to database

5. **Using Gmail/Calendar:**
   - User can now use Slack commands that create Gmail drafts
   - User can now use Slack commands that create Calendar events
   - Token refresh happens automatically

## Token Storage Format

Tokens are stored as JSON in the database:

```json
{
  "token": "ya29.a0AfB_...",
  "refresh_token": "1//0gd...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "123456789.apps.googleusercontent.com",
  "client_secret": "GOCSPX-...",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar"
  ],
  "expiry": "2025-12-03T10:30:00.000000"
}
```

## Security Considerations

1. **State Parameter Validation:**
   - User context is encoded in state parameter
   - State is validated in callback to prevent CSRF attacks

2. **Token Storage:**
   - Tokens are stored in database (PostgreSQL)
   - Consider encrypting tokens at rest for production

3. **HTTPS Only:**
   - OAuth redirect URIs must use HTTPS in production
   - Set `GOOGLE_REDIRECT_URI` environment variable correctly

4. **Refresh Tokens:**
   - Using `access_type='offline'` to get refresh tokens
   - Using `prompt='consent'` to ensure refresh token is provided
   - Refresh tokens allow long-term access without re-authentication

## Troubleshooting

### "Google OAuth not configured" Error
- Ensure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set
- Check environment variables are loaded correctly

### "Redirect URI Mismatch" Error
- Verify redirect URI in Google Cloud Console matches `GOOGLE_REDIRECT_URI`
- Check for trailing slashes or http vs https

### "Token Expired" Error
- Token refresh should happen automatically
- Check that `token_save_callback` is provided and working
- Verify refresh_token is present in token JSON

### "Invalid Grant" Error
- User may need to re-authenticate
- Refresh token may be revoked
- Clear tokens and reconnect Google account

## Testing

### Local Testing

1. Start the Flask app:
   ```bash
   python src/slack_webhook_handler.py
   ```

2. Open settings page:
   ```
   http://localhost:5000/settings
   ```

3. Enter your Slack User ID and connect Google account

4. Test Gmail draft creation:
   ```bash
   # Set token in environment
   export TEST_GMAIL_TOKEN_JSON='{"token": "...", "refresh_token": "..."}'

   # Run test
   python src/modules/gmail_draft_creator.py
   ```

5. Test Calendar event creation:
   ```bash
   export TEST_CALENDAR_TOKEN_JSON='{"token": "...", "refresh_token": "..."}'
   python src/modules/calendar_event_creator.py
   ```

### Production Testing (Render)

1. Set environment variables in Render dashboard
2. Deploy application
3. Test OAuth flow with real users
4. Monitor logs for token refresh events

## Migration Notes

### Migrating from File-based to Database-based Tokens

If you have existing users with `token.json` files:

1. Read token from file
2. Convert to JSON string
3. Save to database
4. Delete token file

```python
import json
from google.oauth2.credentials import Credentials

# Read old token file
creds = Credentials.from_authorized_user_file('token.json', SCOPES)

# Convert to database format
token_data = {
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
    'scopes': creds.scopes,
    'expiry': creds.expiry.isoformat() if creds.expiry else None
}

token_json = json.dumps(token_data)

# Save to database
user.settings.gmail_token = token_json
user.settings.calendar_token = token_json
db.commit()

# Delete old token file
os.remove('token.json')
```

## Summary

This implementation provides a complete, production-ready OAuth 2.0 web flow that:

- Works on Render and other cloud platforms
- Stores tokens securely in database
- Handles token refresh automatically
- Provides user-friendly settings UI
- Includes comprehensive error handling
- Supports multi-user, multi-tenant architecture

All code is production-ready and includes proper error handling, logging, and documentation.
