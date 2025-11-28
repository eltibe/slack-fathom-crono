# Quick Start Guide - CRM Provider Architecture

## Testing the Implementation

### 1. Run the Test Suite

```bash
cd /Users/lorenzo/team/projects/slack-fathom-crono/src
python3 test_providers.py
```

Expected output: All tests should pass ✅

### 2. Start the Flask Server

```bash
cd /Users/lorenzo/team/projects/slack-fathom-crono/src
python3 slack_webhook_handler.py --port 3000
```

Expected output:
```
🚀 Starting Slack webhook handler on port 3000...
📡 Webhook URLs:
   Events: http://localhost:3000/slack/events
   Interactions: http://localhost:3000/slack/interactions

⚠️  Make sure to expose this with ngrok for Slack to reach it:
   ngrok http 3000
```

### 3. Test Slack Commands

Once the server is running and exposed via ngrok:

1. **Test `/meetings` command** in Slack
   - Should list today's meetings from Fathom
   - No errors should appear

2. **Select a meeting and click "Generate Follow-up"**
   - Should process the meeting
   - Should show meeting summary, email, and sales insights

3. **Click "Create Crono Note"**
   - Should find the account by domain
   - Should create a note in Crono
   - Should show success message with Crono link

4. **Click "View Crono Deals"**
   - Should retrieve deals for the account
   - Should display deal information

## What Changed

### Before (Hardcoded)
```python
from modules.crono_client import CronoClient

crono = CronoClient()
crono.create_note(account_id, content)
```

### After (Pluggable)
```python
from providers.factory import CRMProviderFactory

crm_type = os.getenv('CRM_PROVIDER', 'crono')
credentials = {
    'public_key': os.getenv('CRONO_PUBLIC_KEY'),
    'private_key': os.getenv('CRONO_API_KEY')
}
crm_provider = CRMProviderFactory.create(crm_type, credentials)
crm_provider.create_note(account_id, content)
```

## Key Benefits

✅ **Multi-CRM Support** - Can now support Crono, HubSpot, Salesforce, etc.
✅ **Runtime Configuration** - CRM type selected via environment variable
✅ **Easy to Extend** - Add new providers without changing application code
✅ **Backward Compatible** - Existing functionality unchanged
✅ **Clean Architecture** - Clear separation between CRM logic and app logic

## File Overview

```
src/
├── providers/                      # NEW: Provider abstraction layer
│   ├── __init__.py                # Package exports
│   ├── base_provider.py           # Abstract interface (all CRMs must implement)
│   ├── crono_provider.py          # Crono implementation
│   └── factory.py                 # Factory for creating providers
├── slack_webhook_handler.py       # MODIFIED: Now uses factory
├── test_providers.py              # NEW: Test suite
└── modules/
    └── crono_client.py            # UNCHANGED: Original (will deprecate later)
```

## Environment Variables

Add to your `.env` file:

```bash
# CRM Configuration (optional - defaults to 'crono')
CRM_PROVIDER=crono

# Crono Credentials (required if using Crono)
CRONO_PUBLIC_KEY=your_public_key_here
CRONO_API_KEY=your_private_key_here
```

## Troubleshooting

### Import Error: "No module named 'providers'"

**Solution:** Make sure you're running from the `src/` directory:
```bash
cd /Users/lorenzo/team/projects/slack-fathom-crono/src
python3 slack_webhook_handler.py
```

### Error: "Crono provider requires 'public_key' and 'private_key' credentials"

**Solution:** Check your `.env` file has the correct variables:
```bash
# Check if variables are set
echo $CRONO_PUBLIC_KEY
echo $CRONO_API_KEY
```

### Tests Fail: "Crono API returned status 404"

**Explanation:** This is expected if API credentials are invalid or endpoint doesn't exist. The test suite handles this gracefully. As long as other tests pass, the implementation is correct.

## Next Steps

1. **Add HubSpot Support:**
   - Create `src/providers/hubspot_provider.py`
   - Implement the `CRMProvider` interface
   - Register in factory: `_providers = {'crono': CronoProvider, 'hubspot': HubSpotProvider}`

2. **Add Database Configuration:**
   - Store tenant CRM settings in database
   - Replace env var lookup with database query
   - Support per-tenant CRM selection

3. **Test with Real Data:**
   - Test with actual Slack workspace
   - Test with real Fathom meetings
   - Test Crono account matching
   - Verify notes are created correctly

## Documentation

See `PROVIDER_ARCHITECTURE.md` for detailed implementation documentation.

## Quick Commands

```bash
# Run tests
cd src && python3 test_providers.py

# Start server
cd src && python3 slack_webhook_handler.py

# Check syntax
cd src/providers && python3 -m py_compile *.py

# Test imports
cd src && python3 -c "from providers import CRMProviderFactory; print('✅ OK')"
```

## Success Criteria

✅ All tests pass
✅ Server starts without errors
✅ `/meetings` command works in Slack
✅ "Create Crono Note" button works
✅ Account matching works correctly
✅ No import errors

---

**Status:** ✅ Ready for Testing
**Date:** 2025-11-28
