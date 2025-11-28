# Multi-Tenant Integration Guide

## Overview

This guide provides step-by-step instructions for integrating the tenant context middleware into the existing `slack_webhook_handler.py` to transform it from a single-tenant to a multi-tenant application.

## Prerequisites

Before starting:
1. ✅ Database schema implemented (`src/models/`)
2. ✅ Alembic migrations created (`alembic/versions/`)
3. ✅ Tenant middleware implemented (`src/middleware/`)
4. ✅ CRM provider abstraction complete (`src/providers/`)
5. ⏳ Database migrated (see "Data Migration" section below)
6. ⏳ PostgreSQL running and accessible

## Phase 1: Database Setup (30 minutes)

### Step 1.1: Install Dependencies

```bash
cd /Users/lorenzo/team/projects/slack-fathom-crono
pip install -r requirements.txt
```

### Step 1.2: Configure Database

Update `.env`:
```bash
# Database Configuration
DATABASE_URL=postgresql://user:pass@localhost:5432/slack_fathom_crono
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis Configuration (optional, for caching)
REDIS_URL=redis://localhost:6379/0
REDIS_ENABLED=true

# Existing Slack configuration
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
FATHOM_API_KEY=...
ANTHROPIC_API_KEY=...
CRONO_API_KEY=...
CRONO_PUBLIC_KEY=...
```

### Step 1.3: Run Migrations

```bash
# Create database (if not exists)
createdb slack_fathom_crono

# Run migrations
alembic upgrade head

# Verify tables created
psql slack_fathom_crono -c "\dt"
```

Expected output:
```
                List of relations
 Schema |       Name        | Type  |  Owner
--------+-------------------+-------+---------
 public | account_mappings  | table | user
 public | alembic_version   | table | user
 public | api_rate_limits   | table | user
 public | audit_logs        | table | user
 public | crm_connections   | table | user
 public | meeting_sessions  | table | user
 public | tenants           | table | user
 public | users             | table | user
```

---

## Phase 2: Code Integration (2-3 hours)

### Step 2.1: Update Imports in `slack_webhook_handler.py`

**Location**: Lines 1-32

**Add these imports** after line 32:

```python
# Database and multi-tenant support
from database import get_db_session, init_database
from models import Tenant, User, CRMConnection, MeetingSession, AccountMapping
from middleware.flask_middleware import TenantMiddleware
from middleware.tenant_context import get_current_tenant, require_tenant
from middleware.query_helpers import scoped_query, create_scoped
from middleware.exceptions import (
    TenantNotFoundError,
    TenantSuspendedError,
    TenantContextError
)
```

### Step 2.2: Initialize Database and Middleware

**Location**: After line 35 (`app = Flask(__name__)`)

**Replace**:
```python
# Initialize Flask app
app = Flask(__name__)

# Initialize Slack clients
slack_client = SlackClient()
slack_web_client = WebClient(token=os.getenv('SLACK_BOT_TOKEN'))
slash_command_handler = SlackSlashCommandHandler()

# Signature verifier for security
signature_verifier = SignatureVerifier(os.getenv('SLACK_SIGNING_SECRET'))

# In-memory state storage (in production, use Redis or database)
# Format: {thread_ts: {channel, selected_actions, meeting_data, awaiting_confirmation}}
conversation_state = {}
```

**With**:
```python
# Initialize Flask app
app = Flask(__name__)

# Initialize database
init_database()

# Register tenant middleware
tenant_middleware = TenantMiddleware(app)

# Initialize Slack clients (will be per-tenant in handlers)
slack_client = SlackClient()  # Keep for backward compatibility during migration

# DEPRECATED: In-memory state - migrating to database
# TODO: Remove after full migration to MeetingSession table
conversation_state = {}


def get_slack_client_for_tenant():
    """Get Slack client for current tenant."""
    tenant = get_current_tenant()

    # Get Slack credentials from tenant
    token = tenant.get_slack_bot_token()  # This decrypts from AWS Secrets Manager

    return WebClient(token=token)


def get_crm_provider_for_tenant(provider_type: str = None):
    """Get CRM provider for current tenant."""
    tenant = get_current_tenant()

    with get_db_session() as db:
        # Get default CRM connection or specific type
        query = scoped_query(CRMConnection, db).filter_by(status='active')

        if provider_type:
            crm_conn = query.filter_by(provider_type=provider_type).first()
        else:
            crm_conn = query.filter_by(is_default=True).first()

        if not crm_conn:
            raise ValueError(f"No active CRM connection found for tenant")

        # Get credentials from AWS Secrets Manager
        credentials = crm_conn.get_credentials()

        # Create provider using factory
        return CRMProviderFactory.create(crm_conn.provider_type, credentials)
```

### Step 2.3: Update Slash Command Handler

**Location**: Lines 75-140 (`slack_commands()` function)

**Before**:
```python
@app.route('/slack/commands', methods=['POST'])
def slack_commands():
    """Handle Slack slash commands."""

    # Verify the request is from Slack
    if not verify_slack_request(request):
        print("⚠️  Signature verification failed (allowing for debug)")

    # Parse command data
    command = request.form.get('command')
    user_id = request.form.get('user_id')
    channel_id = request.form.get('channel_id')
    response_url = request.form.get('response_url')

    if command == '/followup' or command == '/meetings':
        # Handle command...
        return slash_command_handler.handle_followup_command(
            user_id, channel_id, response_url
        )
```

**After**:
```python
@app.route('/slack/commands', methods=['POST'])
@require_tenant()  # Middleware will set tenant context
def slack_commands():
    """Handle Slack slash commands (multi-tenant)."""

    # Tenant context is already set by middleware
    tenant = get_current_tenant()

    # Parse command data
    command = request.form.get('command')
    user_id = request.form.get('user_id')
    channel_id = request.form.get('channel_id')
    response_url = request.form.get('response_url')

    # Get tenant-specific Slack client
    slack_web_client = get_slack_client_for_tenant()

    # Log command to audit trail
    with get_db_session() as db:
        from models.audit_log import AuditLog
        audit = AuditLog(
            tenant_id=tenant.id,
            event_type='slack.command.received',
            event_category='data_access',
            action_description=f"User {user_id} ran {command}",
            request_data={'command': command, 'channel': channel_id},
            status='success'
        )
        db.add(audit)
        db.commit()

    if command == '/followup' or command == '/meetings':
        return slash_command_handler.handle_followup_command(
            user_id, channel_id, response_url, slack_web_client
        )

    return jsonify({'text': 'Unknown command'}), 200
```

### Step 2.4: Update Interaction Handler

**Location**: Lines 150-250 (`handle_interactive_component()` function)

**Key changes**:

1. **Get tenant context at the start**:
```python
@require_tenant()
def handle_interactive_component(payload):
    tenant = get_current_tenant()
    slack_web_client = get_slack_client_for_tenant()
```

2. **Replace conversation_state with database queries**:

**Before**:
```python
# Get state from in-memory dict
state = conversation_state.get(thread_ts, {})
```

**After**:
```python
# Get state from database
with get_db_session() as db:
    meeting_session = scoped_query(MeetingSession, db).filter_by(
        fathom_recording_id=selected_recording_id
    ).first()

    if not meeting_session:
        # Create new session
        meeting_session = create_scoped(
            MeetingSession,
            db,
            user_id=get_user_db_id(user_id, db),
            fathom_recording_id=selected_recording_id,
            processing_status='pending'
        )
        db.commit()
```

### Step 2.5: Update CRM Note Creation Handler

**Location**: Lines 847-922 (`handle_create_crono_note()`)

**Before**:
```python
def handle_create_crono_note(payload):
    """Create a note in Crono CRM."""

    # Get CRM client with environment credentials
    crm_type = os.getenv('CRM_PROVIDER', 'crono')
    credentials = {
        'public_key': os.getenv('CRONO_PUBLIC_KEY'),
        'private_key': os.getenv('CRONO_API_KEY')
    }
    crm_provider = CRMProviderFactory.create(crm_type, credentials)

    # ... rest of function
```

**After**:
```python
@require_tenant()
def handle_create_crono_note(payload):
    """Create a note in CRM (multi-tenant)."""

    tenant = get_current_tenant()

    # Get CRM provider for tenant (uses default CRM connection)
    try:
        crm_provider = get_crm_provider_for_tenant()
    except ValueError as e:
        return {
            'response_type': 'ephemeral',
            'text': f"❌ No CRM configured for your workspace. Please contact your administrator."
        }

    # Get meeting session from database
    with get_db_session() as db:
        meeting_session = scoped_query(MeetingSession, db).filter_by(
            fathom_recording_id=recording_id
        ).first()

        if not meeting_session:
            return {
                'response_type': 'ephemeral',
                'text': "❌ Meeting session not found"
            }

        # Get or create account mapping
        account_mapping = scoped_query(AccountMapping, db).filter_by(
            email_domain=email_domain,
            crm_connection_id=crm_provider.connection_id
        ).first()

        if account_mapping:
            # Use cached mapping
            crm_account_id = account_mapping.crm_account_id
            # Update usage stats
            account_mapping.times_used += 1
            account_mapping.last_used_at = datetime.utcnow()
        else:
            # Find account via CRM API
            account = crm_provider.find_account_by_domain(email_domain)

            if account:
                # Cache the mapping
                account_mapping = create_scoped(
                    AccountMapping,
                    db,
                    email_domain=email_domain,
                    crm_connection_id=crm_provider.connection_id,
                    crm_account_id=account['id'],
                    crm_account_name=account['name'],
                    mapping_source='auto_discovered',
                    confidence_score=0.95,
                    times_used=1
                )
                crm_account_id = account['id']

        # Create CRM note
        note = crm_provider.create_note(crm_account_id, note_content)

        # Update meeting session
        meeting_session.crm_account_id = crm_account_id
        meeting_session.crm_note_id = note.get('id')
        meeting_session.actions_performed = meeting_session.actions_performed + ['crm_note']
        meeting_session.processing_status = 'completed'

        db.commit()

        # Audit log
        audit = AuditLog(
            tenant_id=tenant.id,
            event_type='crm.note.created',
            event_category='integration',
            resource_type='meeting_session',
            resource_id=meeting_session.id,
            action_description=f"Created CRM note for {crm_account_name}",
            status='success'
        )
        db.add(audit)
        db.commit()
```

### Step 2.6: Update Gmail Draft Handler

**Location**: Lines 655-754 (`handle_create_gmail_draft()`)

**Key changes**:
1. Use tenant-scoped Google OAuth credentials (store in `crm_connections` table with type='google')
2. Store draft ID in `meeting_sessions.gmail_draft_id`
3. Audit log the action

### Step 2.7: Update Calendar Event Handler

**Location**: Lines 757-845 (`handle_create_calendar_event()`)

**Key changes**:
1. Use tenant-scoped Google OAuth credentials
2. Store event ID in `meeting_sessions.calendar_event_id`
3. Audit log the action

---

## Phase 3: Helper Functions (30 minutes)

### Step 3.1: Create Tenant User Mapping

Add this helper function to map Slack user IDs to database user records:

```python
def get_user_db_id(slack_user_id: str, db_session) -> str:
    """Get or create database user record for Slack user."""
    tenant = get_current_tenant()

    # Check if user exists
    user = scoped_query(User, db_session).filter_by(
        slack_user_id=slack_user_id
    ).first()

    if user:
        # Update last active
        user.last_active_at = datetime.utcnow()
        db_session.commit()
        return user.id

    # Fetch user info from Slack
    slack_web_client = get_slack_client_for_tenant()
    try:
        slack_user_info = slack_web_client.users_info(user=slack_user_id)
        user_data = slack_user_info['user']

        # Create new user
        user = create_scoped(
            User,
            db_session,
            slack_user_id=slack_user_id,
            slack_username=user_data.get('name'),
            slack_email=user_data.get('profile', {}).get('email'),
            slack_real_name=user_data.get('real_name'),
            role='member',
            is_active=True
        )
        db_session.commit()

        return user.id
    except Exception as e:
        print(f"Error fetching Slack user info: {e}")
        # Create minimal user record
        user = create_scoped(
            User,
            db_session,
            slack_user_id=slack_user_id,
            role='member',
            is_active=True
        )
        db_session.commit()
        return user.id
```

### Step 3.2: Create Account Mapping Helper

```python
def find_or_create_account_mapping(email_domain: str, company_name: str, db_session):
    """Find account mapping from cache or CRM, and cache result."""
    tenant = get_current_tenant()

    # Try cache first
    crm_conn = scoped_query(CRMConnection, db_session).filter_by(
        is_default=True,
        status='active'
    ).first()

    if not crm_conn:
        raise ValueError("No active CRM connection")

    mapping = scoped_query(AccountMapping, db_session).filter_by(
        email_domain=email_domain,
        crm_connection_id=crm_conn.id
    ).first()

    if mapping:
        # Cache hit - update stats
        mapping.times_used += 1
        mapping.last_used_at = datetime.utcnow()
        db_session.commit()

        return {
            'id': mapping.crm_account_id,
            'name': mapping.crm_account_name,
            'source': 'cache'
        }

    # Cache miss - query CRM
    crm_provider = get_crm_provider_for_tenant()
    account = crm_provider.find_account_by_domain(email_domain, company_name)

    if account:
        # Create cache entry
        mapping = create_scoped(
            AccountMapping,
            db_session,
            email_domain=email_domain,
            crm_connection_id=crm_conn.id,
            crm_account_id=account['id'],
            crm_account_name=account['name'],
            mapping_source='auto_discovered',
            confidence_score=0.90,
            times_used=1,
            last_used_at=datetime.utcnow()
        )
        db_session.commit()

        return {
            'id': account['id'],
            'name': account['name'],
            'source': 'crm_api'
        }

    return None
```

---

## Phase 4: Data Migration (1 hour)

### Step 4.1: Create Initial Tenant

Create a migration script to move your existing single-tenant data:

**File**: `scripts/migrate_to_multitenant.py`

```python
#!/usr/bin/env python3
"""
Migrate single-tenant data to multi-tenant database schema.
"""

import os
import json
from dotenv import load_dotenv
from database import get_db_session, init_database
from models import Tenant, CRMConnection, AccountMapping
from datetime import datetime

load_dotenv()

def migrate():
    """Migrate existing data to multi-tenant schema."""

    init_database()

    with get_db_session() as db:
        # Step 1: Create initial tenant (your Slack workspace)
        slack_team_id = os.getenv('SLACK_TEAM_ID', 'T0123456789')  # Get from Slack
        slack_team_name = os.getenv('SLACK_TEAM_NAME', 'Your Workspace')

        print(f"\n📦 Creating tenant: {slack_team_name} ({slack_team_id})")

        tenant = Tenant(
            slack_team_id=slack_team_id,
            slack_team_name=slack_team_name,
            plan_tier='pro',  # Your current usage level
            subscription_status='active',
            default_crm_provider='crono',
            timezone='Europe/Rome',
            locale='it',
            installed_at=datetime.utcnow()
        )
        db.add(tenant)
        db.commit()

        print(f"✅ Tenant created: {tenant.id}")

        # Step 2: Store Slack credentials in AWS Secrets Manager
        # (This requires AWS CLI configured)
        # For now, we'll store a placeholder

        tenant.slack_bot_token_secret_id = 'placeholder_update_manually'
        db.commit()

        print(f"⚠️  TODO: Store Slack bot token in AWS Secrets Manager")
        print(f"   Run: aws secretsmanager create-secret --name slack-bot-token-{tenant.id} --secret-string '<token>'")

        # Step 3: Create CRM connection for Crono
        print(f"\n📦 Creating Crono CRM connection")

        crono_conn = CRMConnection(
            tenant_id=tenant.id,
            provider_type='crono',
            connection_name='Crono Production',
            credentials_secret_id='placeholder_update_manually',  # Store in AWS Secrets Manager
            status='active',
            is_default=True
        )
        db.add(crono_conn)
        db.commit()

        print(f"✅ CRM connection created: {crono_conn.id}")
        print(f"⚠️  TODO: Store Crono credentials in AWS Secrets Manager")
        print(f"   Run: aws secretsmanager create-secret --name crono-creds-{crono_conn.id} --secret-string '{{\"public_key\":\"...\",\"private_key\":\"...\"}}'")

        # Step 4: Migrate account mappings from JSON file
        mappings_file = 'configs/account_mappings.json'
        if os.path.exists(mappings_file):
            print(f"\n📦 Migrating account mappings from {mappings_file}")

            with open(mappings_file, 'r') as f:
                mappings_data = json.load(f)

            domain_to_account = mappings_data.get('domain_to_account', {})

            for domain, account_name in domain_to_account.items():
                mapping = AccountMapping(
                    tenant_id=tenant.id,
                    crm_connection_id=crono_conn.id,
                    email_domain=domain,
                    company_name=account_name,
                    crm_account_id='unknown',  # Will be resolved on first use
                    crm_account_name=account_name,
                    mapping_source='imported',
                    verified=True,  # Manually configured
                    times_used=0
                )
                db.add(mapping)

            db.commit()
            print(f"✅ Migrated {len(domain_to_account)} account mappings")

        # Step 5: Summary
        print(f"\n" + "="*60)
        print(f"✅ Migration Complete!")
        print(f"="*60)
        print(f"\nTenant ID: {tenant.id}")
        print(f"Slack Team ID: {tenant.slack_team_id}")
        print(f"CRM Connection ID: {crono_conn.id}")
        print(f"\nNext Steps:")
        print(f"1. Store credentials in AWS Secrets Manager (see commands above)")
        print(f"2. Update .env with TENANT_ID={tenant.id}")
        print(f"3. Restart the Flask server")
        print(f"4. Test with /meetings command in Slack")
        print(f"\n" + "="*60)

if __name__ == '__main__':
    migrate()
```

**Run migration**:
```bash
python scripts/migrate_to_multitenant.py
```

### Step 4.2: Update Environment Variables

After migration, add to `.env`:
```bash
# Initial tenant (for development/testing)
SLACK_TEAM_ID=T0123456789  # Your actual Slack team ID
SLACK_TEAM_NAME=Your Workspace Name
INITIAL_TENANT_ID=<uuid-from-migration>
```

---

## Phase 5: Testing (1-2 hours)

### Step 5.1: Test Middleware

```bash
cd src
python test_tenant_middleware.py
```

Expected output:
```
========================================
Testing Tenant Context Middleware
========================================

[Test 1] Thread-local context isolation
✅ Thread-local context isolation works

[Test 2] Slack request parsing (slash command)
✅ Slack team_id extracted: T0123456789

[Test 3] Tenant loading from database
✅ Tenant loaded: Your Workspace (T0123456789)

... (8 tests total)

========================================
✅ ALL TESTS PASSED!
========================================
```

### Step 5.2: Test Database Models

```bash
cd src
python test_database.py
```

### Step 5.3: Test End-to-End in Slack

1. **Restart server**:
```bash
cd src
lsof -ti:3000 | xargs kill
python slack_webhook_handler.py > ../followup_webhook.log 2>&1 &
```

2. **In Slack, run**: `/meetings`
   - Verify meetings load
   - Check logs for tenant context

3. **Select a meeting and click "Generate Follow-up"**
   - Verify AI processing works
   - Check database for meeting_session record

4. **Click "Create Crono Note"**
   - Verify account mapping lookup
   - Check database for cached mapping
   - Verify note created in Crono

5. **Monitor logs**:
```bash
tail -f followup_webhook.log
```

Look for:
```
🔐 Tenant context set: Your Workspace (T0123456789)
📊 Database query: MeetingSession.filter_by(tenant_id=...)
✅ Account mapping cache hit: neuronup.com → NeuronUP
```

---

## Phase 6: Production Deployment

### Step 6.1: AWS Secrets Manager Setup

Store sensitive credentials in AWS Secrets Manager:

```bash
# Slack Bot Token
aws secretsmanager create-secret \
  --name "slack-bot-token-${TENANT_ID}" \
  --description "Slack Bot Token for tenant ${TENANT_ID}" \
  --secret-string "xoxb-your-token-here"

# Crono API Credentials
aws secretsmanager create-secret \
  --name "crono-credentials-${CRM_CONNECTION_ID}" \
  --description "Crono API credentials" \
  --secret-string '{
    "public_key": "cpk_...",
    "private_key": "csk_..."
  }'
```

### Step 6.2: Update Models to Fetch from Secrets Manager

In `models/tenant.py`:
```python
import boto3

def get_slack_bot_token(self) -> str:
    """Decrypt and return Slack bot token from AWS Secrets Manager."""
    if not self.slack_bot_token_secret_id:
        raise ValueError("No Slack bot token configured")

    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=self.slack_bot_token_secret_id)

    return response['SecretString']
```

In `models/crm_connection.py`:
```python
def get_credentials(self) -> dict:
    """Decrypt and return CRM credentials from AWS Secrets Manager."""
    if not self.credentials_secret_id:
        raise ValueError("No credentials configured")

    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=self.credentials_secret_id)

    return json.loads(response['SecretString'])
```

### Step 6.3: Update requirements.txt

```bash
boto3==1.34.0
botocore==1.34.0
```

---

## Rollback Plan

If issues arise, you can rollback quickly:

### Option 1: Feature Flag (Recommended)

Add to `.env`:
```bash
MULTI_TENANT_ENABLED=false
```

In `slack_webhook_handler.py`:
```python
if os.getenv('MULTI_TENANT_ENABLED', 'false').lower() == 'true':
    # Use multi-tenant code path
    tenant_middleware = TenantMiddleware(app)
else:
    # Use single-tenant code path (legacy)
    pass
```

### Option 2: Git Revert

```bash
git log --oneline | head -5  # Find commit before multi-tenant
git revert <commit-hash>
```

---

## Troubleshooting

### Issue: "Tenant not found"

**Symptoms**: 403 error with `{"error": "Workspace not installed"}`

**Solution**:
1. Check tenant exists in database:
```sql
SELECT * FROM tenants WHERE slack_team_id = 'T0123456789';
```

2. If missing, run migration script again

3. Clear Redis cache:
```bash
redis-cli FLUSHDB
```

### Issue: "CRM connection not found"

**Symptoms**: ValueError about no CRM connection

**Solution**:
1. Check CRM connection exists:
```sql
SELECT * FROM crm_connections WHERE tenant_id = '<tenant-uuid>' AND status = 'active';
```

2. Create connection manually:
```python
python scripts/create_crm_connection.py --tenant-id <uuid> --provider crono
```

### Issue: "AWS Secrets Manager access denied"

**Symptoms**: `botocore.exceptions.ClientError: AccessDeniedException`

**Solution**:
1. Configure AWS credentials:
```bash
aws configure
```

2. Or use IAM role (recommended for EC2/ECS)

3. Grant permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "secretsmanager:GetSecretValue"
    ],
    "Resource": "arn:aws:secretsmanager:*:*:secret:slack-*"
  }]
}
```

---

## Performance Considerations

### Database Query Optimization

1. **Use database connection pooling** (already configured in `database.py`)
2. **Index tenant_id columns** (already created in migrations)
3. **Use Redis caching** for tenant lookups (5-minute TTL)
4. **Batch queries** when processing multiple meetings

### Monitoring

Add logging for performance metrics:

```python
import time

def timeit(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start

        print(f"⏱️  {func.__name__} took {duration:.2f}s")

        # Log to CloudWatch/Datadog
        if duration > 1.0:
            print(f"⚠️  Slow query detected: {func.__name__}")

        return result
    return wrapper

@timeit
def find_or_create_account_mapping(email_domain, company_name, db_session):
    # ... implementation
```

---

## Security Checklist

- [ ] All Slack requests verified with signature
- [ ] Tenant context enforced on all routes
- [ ] Database queries filtered by tenant_id
- [ ] Credentials stored in AWS Secrets Manager (not database)
- [ ] Audit logging enabled for all critical operations
- [ ] Rate limiting per tenant configured
- [ ] HTTPS enforced (via ngrok or ALB)
- [ ] Environment variables not committed to git
- [ ] PostgreSQL uses SSL connections
- [ ] Redis uses AUTH password

---

## Next Steps After Integration

1. **Phase 7: HubSpot Integration**
   - Implement HubSpotProvider in `src/providers/hubspot_provider.py`
   - Add OAuth flow for HubSpot connection
   - Test with HubSpot sandbox account

2. **Phase 8: Web Application**
   - Build landing page
   - Create dashboard for tenant management
   - Implement Slack app installation flow
   - Add CRM connection UI

3. **Phase 9: Production Hardening**
   - Set up AWS infrastructure (ECS, RDS, Redis)
   - Configure CloudWatch monitoring
   - Implement backup/restore procedures
   - Load testing and performance optimization

4. **Phase 10: Launch**
   - Beta testing with 5-10 workspaces
   - Gather feedback and iterate
   - Public launch 🚀

---

## Support

If you encounter issues during integration:
1. Check logs: `tail -f followup_webhook.log`
2. Test middleware: `python src/test_tenant_middleware.py`
3. Review this guide's Troubleshooting section
4. Check database state manually with psql

---

**Document Version**: 1.0
**Last Updated**: 2025-11-28
**Status**: ✅ Ready for Integration
**Estimated Time**: 4-6 hours total
