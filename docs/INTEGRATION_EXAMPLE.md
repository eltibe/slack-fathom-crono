# Tenant Middleware Integration Example

This document shows specific code changes needed to integrate the tenant middleware into the existing `slack_webhook_handler.py`.

## Changes to `slack_webhook_handler.py`

### 1. Add Imports at the Top

```python
# Add these imports after existing imports
from middleware import (
    TenantMiddleware,
    get_current_tenant,
    get_current_tenant_id,
    scoped_query,
    create_scoped,
    verify_tenant_access
)
from models import CRMConnection
```

### 2. Register Middleware After App Initialization

```python
# After: app = Flask(__name__)
app = Flask(__name__)

# ADD THIS: Register tenant middleware
middleware = TenantMiddleware(
    app,
    verify_signatures=True,  # Enable Slack signature verification
    enable_logging=True      # Enable request logging
)
middleware.register()

# Continue with existing code...
slack_client = SlackClient()
```

### 3. Update verify_slack_request() Function

The middleware now handles signature verification, but if you want to keep the function for backward compatibility:

```python
def verify_slack_request(request) -> bool:
    """
    Verify that the request is from Slack using signature verification.

    NOTE: The TenantMiddleware already performs this check, but this function
    is kept for backward compatibility and explicit verification in handlers.
    """
    # The middleware has already verified the signature at this point
    # So this function can just return True or delegate to middleware
    from middleware.slack_parser import verify_slack_signature
    return verify_slack_signature(request)
```

### 4. Update handle_create_crono_note() Function

**BEFORE (hardcoded CRM credentials)**:
```python
def create_note_in_background():
    try:
        # TODO: Get tenant's CRM type and credentials from database
        # For now, use Crono with env variables (backward compatible)
        crm_type = os.getenv('CRM_PROVIDER', 'crono')
        credentials = {
            'public_key': os.getenv('CRONO_PUBLIC_KEY'),
            'private_key': os.getenv('CRONO_API_KEY')
        }
        crm_provider = CRMProviderFactory.create(crm_type, credentials)
```

**AFTER (tenant-scoped CRM)**:
```python
def create_note_in_background():
    try:
        # Get tenant's CRM connection from database
        from database import get_session
        from middleware import get_current_tenant, scoped_query
        from models import CRMConnection

        tenant = get_current_tenant()

        # Get database session
        with get_session() as db:
            # Get default CRM connection for this tenant
            crm_conn = scoped_query(CRMConnection, db).filter_by(
                is_default=True
            ).first()

            if not crm_conn:
                logger.error(f"No CRM connection found for tenant {tenant.slack_team_id}")
                if response_url:
                    requests.post(response_url, json={
                        "response_type": "ephemeral",
                        "replace_original": False,
                        "text": "⚠️ CRM not configured for this workspace. Please contact support."
                    }, timeout=5)
                return

            # Create CRM provider with tenant's credentials
            crm_provider = CRMProviderFactory.create(
                crm_conn.provider_type,
                crm_conn.get_credentials()
            )

            # Rest of the function remains the same...
```

### 5. Update handle_view_crono_deals() Function

Same pattern as above:

```python
def view_deals_in_background():
    try:
        from database import get_session
        from middleware import get_current_tenant, scoped_query
        from models import CRMConnection

        tenant = get_current_tenant()

        with get_session() as db:
            crm_conn = scoped_query(CRMConnection, db).filter_by(
                is_default=True
            ).first()

            if not crm_conn:
                # Handle missing CRM connection
                return

            crm_provider = CRMProviderFactory.create(
                crm_conn.provider_type,
                crm_conn.get_credentials()
            )

            # Rest of function...
```

### 6. Update execute_selected_actions() Function

Same pattern for Crono note creation:

```python
# Execute Crono Note
if 'crono_note' in selected_actions:
    try:
        from database import get_session
        from middleware import get_current_tenant, scoped_query
        from models import CRMConnection

        with get_session() as db:
            tenant = get_current_tenant()

            crm_conn = scoped_query(CRMConnection, db).filter_by(
                is_default=True
            ).first()

            if not crm_conn:
                results['crono_note'] = False
                details['crono_note'] = "CRM not configured"
            else:
                crm_provider = CRMProviderFactory.create(
                    crm_conn.provider_type,
                    crm_conn.get_credentials()
                )

                # Rest of Crono note creation...
```

### 7. Store Meeting Data with Tenant Context

When storing meeting data in `conversation_state`, also store the tenant context:

```python
# In process_selected_meeting():
conversation_state[recording_id] = {
    'meeting_title': meeting_title,
    'final_email': final_email,
    'meeting_summary': meeting_summary,
    'sales_data': sales_data,
    'external_emails': external_emails,
    'meeting_url': meeting_url,
    'meeting_data': meeting_data,
    'transcript': transcript,
    'channel': channel,
    'user_id': user_id,
    # ADD THIS: Store tenant info for background processing
    'tenant_id': str(get_current_tenant_id()),
    'slack_team_id': get_current_tenant().slack_team_id
}
```

### 8. Add Meeting Session Recording (Optional but Recommended)

Track meeting processing in the database:

```python
# In process_selected_meeting(), after generating content:
from middleware import create_scoped
from models import MeetingSession

with get_session() as db:
    # Create meeting session record
    meeting_session = create_scoped(
        MeetingSession,
        db,
        fathom_recording_id=recording_id,
        meeting_title=meeting_title,
        processed_at=datetime.utcnow(),
        user_id=None,  # Or get from User table
        email_generated=True,
        calendar_event_created=False,
        crm_note_created=False
    )
    db.add(meeting_session)
    db.commit()
```

### 9. Update Background Thread Context

When spawning background threads, you need to pass tenant context:

```python
# BEFORE:
thread = threading.Thread(target=create_note_in_background)
thread.start()

# AFTER:
from middleware import get_current_tenant

# Capture tenant before spawning thread
current_tenant = get_current_tenant()

def create_note_in_background_with_context():
    # Set tenant context in new thread
    from middleware import set_current_tenant
    set_current_tenant(current_tenant)

    try:
        create_note_in_background()
    finally:
        # Clean up context
        from middleware import clear_tenant_context
        clear_tenant_context()

thread = threading.Thread(target=create_note_in_background_with_context)
thread.start()
```

### 10. Add Health Check Route (Whitelisted)

```python
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint (whitelisted - no tenant required)."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })
```

## Complete Example: Updated Button Handler

Here's a complete example of an updated button handler with all best practices:

```python
def handle_create_crono_note(payload: Dict):
    """Handle when user clicks 'Create Crono Note' button."""
    import sys
    import requests
    from database import get_session
    from middleware import get_current_tenant, scoped_query
    from models import CRMConnection

    try:
        # Get recording_id from button value
        recording_id = payload['actions'][0]['value']
        response_url = payload.get('response_url')

        sys.stderr.write(f"📝 Creating Crono note for recording {recording_id}...\n")
        sys.stderr.flush()

        # Retrieve stored meeting data
        if recording_id not in conversation_state:
            sys.stderr.write(f"❌ No data found for recording {recording_id}\n")
            sys.stderr.flush()
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "❌ Meeting data not found. Please try processing the meeting again."
            })

        state = conversation_state[recording_id]
        meeting_title = state['meeting_title']
        sales_data = state['sales_data']
        meeting_url = state['meeting_url']
        external_emails = state['external_emails']

        if not external_emails:
            return jsonify({
                "response_type": "ephemeral",
                "replace_original": False,
                "text": "⚠️ No external attendees found. Cannot determine which CRM account to add note to."
            })

        # Capture tenant context for background thread
        current_tenant = get_current_tenant()

        # Process in background
        import threading

        def create_note_in_background():
            # Set tenant context in background thread
            from middleware import set_current_tenant, clear_tenant_context
            set_current_tenant(current_tenant)

            try:
                sys.stderr.write(f"🔄 Creating CRM note in background...\n")
                sys.stderr.flush()

                # Get tenant's CRM connection
                with get_session() as db:
                    crm_conn = scoped_query(CRMConnection, db).filter_by(
                        is_default=True
                    ).first()

                    if not crm_conn:
                        sys.stderr.write(f"⚠️ No CRM connection for tenant {current_tenant.slack_team_id}\n")
                        sys.stderr.flush()

                        if response_url:
                            requests.post(response_url, json={
                                "response_type": "ephemeral",
                                "replace_original": False,
                                "text": "⚠️ CRM not configured. Please configure a CRM connection first."
                            }, timeout=5)
                        return

                    # Create CRM provider with tenant's credentials
                    crm_provider = CRMProviderFactory.create(
                        crm_conn.provider_type,
                        crm_conn.get_credentials()
                    )

                    # Find account by domain
                    email_domain = external_emails[0].split('@')[-1]
                    company_name_raw = email_domain.split('.')[0]

                    account = crm_provider.find_account_by_domain(
                        email_domain=email_domain,
                        company_name=company_name_raw
                    )

                    if not account:
                        sys.stderr.write(f"⚠️ No CRM account found for domain {email_domain}\n")
                        sys.stderr.flush()

                        if response_url:
                            requests.post(response_url, json={
                                "response_type": "ephemeral",
                                "replace_original": False,
                                "text": f"⚠️ No CRM account found for domain '{email_domain}'.\n\nPlease create the account in your CRM first."
                            }, timeout=5)
                        return

                    account_id = account.get('objectId') or account.get('id')
                    account_name = account.get('name', 'Unknown')

                    sys.stderr.write(f"✅ Found CRM account: {account_name} ({account_id})\n")
                    sys.stderr.flush()

                    # Create meeting summary note
                    note_id = crm_provider.create_meeting_summary(
                        account_id=account_id,
                        meeting_title=meeting_title,
                        summary_data=sales_data,
                        meeting_url=meeting_url
                    )

                    if note_id:
                        sys.stderr.write(f"✅ CRM note created: {note_id}\n")
                        sys.stderr.flush()

                        # Record in database
                        from models import MeetingSession
                        meeting_session = scoped_query(MeetingSession, db).filter_by(
                            fathom_recording_id=recording_id
                        ).first()

                        if meeting_session:
                            meeting_session.crm_note_created = True
                            meeting_session.crm_note_id = note_id
                            db.commit()

                        success_text = f"✅ CRM note created successfully!\n\nAccount: {account_name}\nMeeting: {meeting_title}"
                        if response_url:
                            requests.post(response_url, json={
                                "response_type": "ephemeral",
                                "replace_original": False,
                                "text": success_text
                            }, timeout=5)

            except Exception as e:
                sys.stderr.write(f"❌ Error creating CRM note: {e}\n")
                sys.stderr.flush()
                import traceback
                traceback.print_exc(file=sys.stderr)

                if response_url:
                    requests.post(response_url, json={
                        "response_type": "ephemeral",
                        "replace_original": False,
                        "text": f"❌ Error creating CRM note: {str(e)}"
                    }, timeout=5)

            finally:
                # Clean up tenant context
                clear_tenant_context()

        thread = threading.Thread(target=create_note_in_background)
        thread.start()

        # Return immediate acknowledgment
        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": "⏳ Creating CRM note... This may take a few seconds."
        })

    except Exception as e:
        sys.stderr.write(f"❌ Error in handle_create_crono_note: {e}\n")
        sys.stderr.flush()
        import traceback
        traceback.print_exc(file=sys.stderr)

        return jsonify({
            "response_type": "ephemeral",
            "replace_original": False,
            "text": f"❌ Error: {str(e)}"
        })
```

## Testing the Integration

### 1. Test Middleware Registration

```python
# Add to slack_webhook_handler.py at the bottom:
if __name__ == "__main__":
    print("Middleware registered:", middleware is not None)
    print("Whitelisted routes:", middleware.whitelist_routes)

    # Test with sample request
    with app.test_request_context():
        from flask import request
        print("App ready for testing")
```

### 2. Test with curl

```bash
# Test health check (should work without tenant)
curl http://localhost:3000/health

# Test with Slack signature (will fail without valid signature)
curl -X POST http://localhost:3000/slack/commands \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "team_id=T0123456789&command=/followup"
```

### 3. Run Unit Tests

```bash
python src/test_tenant_middleware.py --verbose
```

## Common Migration Issues

### Issue 1: Background Threads Lose Tenant Context

**Problem**: Background threads don't have tenant context.

**Solution**: Pass tenant to thread and set context:
```python
current_tenant = get_current_tenant()

def background_task():
    set_current_tenant(current_tenant)
    try:
        # Do work
        pass
    finally:
        clear_tenant_context()
```

### Issue 2: Database Session Management

**Problem**: Database sessions not properly closed in background threads.

**Solution**: Always use context manager:
```python
with get_session() as db:
    # Work with db
    db.commit()
# Session automatically closed
```

### Issue 3: CRM Credentials Not Found

**Problem**: No CRM connection record for tenant.

**Solution**: Create default CRM connection during onboarding:
```python
from models import CRMConnection

# During OAuth callback or app installation:
crm_conn = create_scoped(
    CRMConnection,
    db,
    provider_type='crono',
    is_default=True,
    credentials_secret_id='...'  # AWS Secrets Manager ID
)
db.add(crm_conn)
db.commit()
```

## Rollout Plan

1. **Deploy middleware (non-breaking)**: Register middleware but don't change handlers yet
2. **Test in staging**: Verify requests work with middleware
3. **Update handlers one by one**: Start with less critical handlers
4. **Monitor metrics**: Watch error rates and performance
5. **Complete migration**: Update all handlers to use tenant-scoped queries

## Next Steps

1. Complete integration following this guide
2. Run test suite: `python src/test_tenant_middleware.py`
3. Test in development environment
4. Deploy to staging
5. Monitor for issues
6. Deploy to production

For questions or issues, refer to the main documentation: `docs/TENANT_MIDDLEWARE.md`
