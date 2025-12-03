# Google OAuth Quick Start Guide

## Setup (One-Time)

### 1. Google Cloud Console

1. Go to https://console.cloud.google.com/
2. Create OAuth 2.0 credentials (Web application)
3. Add redirect URI: `https://your-domain.com/oauth/google/callback`
4. Enable Gmail API and Google Calendar API
5. Copy Client ID and Client Secret

### 2. Environment Variables

Add to `.env` and Render:

```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-secret
GOOGLE_REDIRECT_URI=https://your-domain.com/oauth/google/callback
```

## User Flow

1. User visits `/settings`
2. Enters Slack User ID
3. Clicks "Gmail" tab
4. Clicks "Connetti Account Google"
5. Authenticates with Google
6. Tokens saved to database
7. Can now use Gmail/Calendar features

## Developer Usage

### Gmail Draft Creation

```python
from src.modules.gmail_draft_creator import GmailDraftCreator

# Get user's token from database
token_json = user.settings.gmail_token

# Define save callback for token refresh
def save_token(new_token):
    user.settings.gmail_token = new_token
    db.commit()

# Create Gmail client
gmail = GmailDraftCreator(token_json, save_token)

# Create draft
draft_id = gmail.create_draft(
    subject="Meeting Follow-up",
    body="<p>Thank you for meeting...</p>",
    to=["recipient@example.com"]
)
```

### Calendar Event Creation

```python
from src.modules.calendar_event_creator import CalendarEventCreator
from datetime import datetime, timedelta
import pytz

# Get user's token from database
token_json = user.settings.calendar_token

# Define save callback
def save_token(new_token):
    user.settings.calendar_token = new_token
    db.commit()

# Create Calendar client
calendar = CalendarEventCreator(token_json, save_token)

# Create event
event_id = calendar.create_followup_meeting(
    title="Follow-up Meeting",
    start_datetime=datetime.now(pytz.UTC) + timedelta(days=7),
    duration_minutes=30,
    attendees=["team@example.com"],
    description="Follow-up discussion"
)
```

## API Endpoints

### Start OAuth Flow
```
GET /oauth/google/start?slack_user_id=U01234567
```

### Check Connection Status
```
GET /api/google/status?slack_user_id=U01234567
```

Response:
```json
{
  "connected": true,
  "email": "user@example.com"
}
```

### Disconnect Account
```
POST /api/google/disconnect
Content-Type: application/json

{
  "slack_user_id": "U01234567"
}
```

## Error Handling

### User Not Connected
```python
if not user.settings or not user.settings.gmail_token:
    return jsonify({
        "error": "Please connect your Google account at /settings"
    }), 400
```

### Token Refresh Failed
```python
try:
    gmail = GmailDraftCreator(token_json, save_token)
except ValueError as e:
    return jsonify({"error": f"Invalid token: {e}"}), 400
except Exception as e:
    logger.error(f"Gmail auth failed: {e}")
    return jsonify({
        "error": "Authentication failed. Please reconnect your Google account."
    }), 500
```

## Testing Locally

1. Start app: `python src/slack_webhook_handler.py`
2. Visit: `http://localhost:5000/settings`
3. Set `GOOGLE_REDIRECT_URI=http://localhost:5000/oauth/google/callback`
4. Connect Google account
5. Test draft creation: `python src/modules/gmail_draft_creator.py`

## Common Issues

**"Redirect URI mismatch"**
- Check `GOOGLE_REDIRECT_URI` matches Google Cloud Console
- Ensure http/https protocol matches

**"Invalid grant"**
- User needs to re-authenticate
- Clear tokens and reconnect in `/settings`

**"Token expired"**
- Should auto-refresh (check save callback is working)
- Check database connection in callback

## Key Changes from Old Implementation

| Old (File-based) | New (Database-backed) |
|-----------------|----------------------|
| `GmailDraftCreator()` | `GmailDraftCreator(token_json, save_callback)` |
| `credentials.json` file | Environment variables |
| `token.json` file | Database column |
| `run_local_server()` | Web OAuth flow |
| Single user | Multi-user/tenant |
| Local only | Works on Render |

## Security Notes

- Tokens stored in database (consider encryption)
- State parameter prevents CSRF attacks
- HTTPS required in production
- Refresh tokens enable long-term access
- User can disconnect anytime

For complete documentation, see `GOOGLE_OAUTH_SETUP.md`
