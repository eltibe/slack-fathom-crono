## Tenant Context Middleware Documentation

# Multi-Tenant Architecture

This document describes the tenant isolation middleware system that ensures complete data separation between Slack workspaces in our multi-tenant SaaS application.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [How It Works](#how-it-works)
3. [Components](#components)
4. [Integration Guide](#integration-guide)
5. [Security](#security)
6. [Performance](#performance)
7. [Troubleshooting](#troubleshooting)
8. [Migration Guide](#migration-guide)

---

## Architecture Overview

### The Problem

In a multi-tenant SaaS application, each Slack workspace is an isolated tenant with its own data. We must ensure:

- **Data Isolation**: Tenant A cannot access Tenant B's data
- **Security**: All database queries are automatically scoped to the correct tenant
- **Performance**: Minimal overhead for tenant context management
- **Reliability**: Thread-safe operation in concurrent request environments

### The Solution

A middleware system that:

1. Extracts tenant information from every Slack webhook request
2. Loads tenant from database (with caching)
3. Stores tenant in thread-local context for the request lifecycle
4. Provides helper functions that automatically scope all database queries
5. Cleans up context after request completion

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Slack Webhook                          │
│         (slash command, interaction, event)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Flask before_request Handler                   │
│  1. Extract team_id from request                            │
│  2. Verify Slack signature                                  │
│  3. Load tenant from cache/DB                               │
│  4. Set tenant in thread-local context                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Request Handler Executes                       │
│  - Uses get_current_tenant() to access tenant               │
│  - Uses scoped_query() for all database queries             │
│  - All operations automatically scoped to tenant            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Flask after_request Handler                    │
│  1. Clear tenant context                                    │
│  2. Close database session                                  │
│  3. Return response                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## How It Works

### Request Flow Example

Let's trace a request through the system:

```python
# 1. Slack sends webhook
POST /slack/commands
Content-Type: application/x-www-form-urlencoded
X-Slack-Signature: v0=a2114d...
X-Slack-Request-Timestamp: 1531420618

team_id=T0123456789&command=/followup&user_id=U9876543210

# 2. Flask before_request → TenantMiddleware.process_request()
#    - Verify signature: ✓
#    - Extract team_id: T0123456789
#    - Check Redis cache: MISS
#    - Query database:
      SELECT * FROM tenants
      WHERE slack_team_id = 'T0123456789'
      AND deleted_at IS NULL
#    - Found tenant: Acme Corp (uuid: 123e4567-...)
#    - Cache in Redis (TTL: 5 min)
#    - Set thread-local context: set_current_tenant(tenant)
#    - Attach to Flask g: g.tenant = tenant

# 3. Request handler executes
@app.route('/slack/commands')
def slack_commands():
    tenant = get_current_tenant()  # Returns: Tenant(id=123e4567..., name=Acme Corp)

    # All queries automatically scoped:
    meetings = scoped_query(MeetingSession, db).filter(
        MeetingSession.created_at > last_week
    ).all()

    # Equivalent to:
    # SELECT * FROM meeting_sessions
    # WHERE tenant_id = '123e4567-...'
    # AND created_at > '...'
    # AND deleted_at IS NULL

# 4. Flask after_request → TenantMiddleware.cleanup_request()
#    - Clear context: clear_tenant_context()
#    - Close DB session
#    - Return response
```

### Thread Isolation

Each HTTP request runs in its own thread with isolated tenant context:

```
Thread 1 (Request from Tenant A):
  thread_local.tenant = Tenant A
  → All queries scoped to Tenant A

Thread 2 (Request from Tenant B):
  thread_local.tenant = Tenant B
  → All queries scoped to Tenant B

Thread 3 (Request from Tenant A):
  thread_local.tenant = Tenant A
  → All queries scoped to Tenant A

(Completely isolated - no cross-contamination)
```

---

## Components

### 1. `tenant_context.py` - Thread-Local Context Manager

**Purpose**: Store and manage current tenant in thread-local storage.

**Key Functions**:

```python
# Set tenant for current request
set_current_tenant(tenant)

# Get tenant anywhere in request handling
tenant = get_current_tenant()

# Get just the tenant ID
tenant_id = get_current_tenant_id()

# Clear context (cleanup)
clear_tenant_context()

# Context manager
with tenant_context(tenant):
    # Code here has tenant set
    process_data()

# Decorator
@require_tenant()
def my_handler():
    tenant = get_current_tenant()
    # tenant is guaranteed to be set
```

**Implementation Details**:
- Uses `threading.local()` for thread safety
- Stores full Tenant model instance
- Raises `TenantContextError` if accessed without tenant set
- Provides logging integration for structured logs

---

### 2. `slack_parser.py` - Request Parser

**Purpose**: Extract tenant ID from various Slack webhook formats.

**Supported Request Types**:

1. **Slash Commands** (form data):
   ```
   team_id=T0123456789&command=/followup
   ```

2. **Interactions** (JSON in form data):
   ```
   payload={"team":{"id":"T0123456789"},"type":"block_actions"}
   ```

3. **Events API** (JSON body):
   ```json
   {"team_id": "T0123456789", "type": "event_callback"}
   ```

**Key Functions**:

```python
# Extract team_id from any request type
team_id = extract_tenant_id_from_request(request)

# Verify Slack signature (security)
is_valid = verify_slack_signature(request)

# Parse specific request types
cmd_data = parse_slash_command(request)
interaction = parse_interaction(request)
event = parse_event(request)
```

**Security Features**:
- HMAC-SHA256 signature verification
- Timestamp validation (5-minute window)
- Replay attack prevention
- Constant-time comparison

---

### 3. `tenant_loader.py` - Database Loader with Caching

**Purpose**: Load tenants from database with Redis caching.

**Key Functions**:

```python
# Load tenant by Slack team ID
tenant = load_tenant_by_slack_id("T0123456789", db)

# Get or create tenant (auto-provisioning)
tenant = get_or_create_tenant(
    slack_team_id="T0123456789",
    team_name="Acme Corp",
    db_session=db
)

# Clear cache
clear_tenant_cache("T0123456789")  # Specific tenant
clear_tenant_cache()               # All tenants

# Refresh tenant and cache
tenant = refresh_tenant(tenant, db)

# Warm up cache at startup
count = preload_tenants(db, limit=500)
```

**Caching Strategy**:
- Redis key: `tenant:slack_id:{slack_team_id}`
- TTL: 5 minutes (configurable)
- Graceful degradation if Redis unavailable
- Automatic cache invalidation on updates

**Performance**:
- Cache HIT: ~1-2ms
- Cache MISS: ~50-100ms (DB query)
- Without Redis: ~50-100ms (direct DB)

---

### 4. `flask_middleware.py` - Flask Integration

**Purpose**: Integrate tenant middleware with Flask request lifecycle.

**Usage**:

```python
from flask import Flask
from middleware import TenantMiddleware

app = Flask(__name__)
middleware = TenantMiddleware(app)
middleware.register()

# Or with init_app pattern:
middleware = TenantMiddleware()
middleware.init_app(app)
```

**Whitelisted Routes** (no tenant required):
- `/health`
- `/metrics`
- `/static/*`
- `/favicon.ico`

**Error Responses**:

```json
// Tenant not found (403)
{
  "error": "Workspace not installed",
  "code": "TENANT_NOT_FOUND",
  "slack_team_id": "T0123456789"
}

// Tenant suspended (403)
{
  "error": "Subscription suspended",
  "code": "TENANT_SUSPENDED",
  "subscription_status": "suspended"
}

// Invalid signature (403)
{
  "error": "Invalid request signature",
  "code": "INVALID_SIGNATURE"
}
```

---

### 5. `query_helpers.py` - Tenant-Scoped Queries

**Purpose**: Ensure all database queries are automatically scoped to current tenant.

**Critical Security Functions**:

```python
# ALWAYS use scoped_query() instead of db.query()
# BAD (returns ALL tenants' data):
meetings = db.query(MeetingSession).all()

# GOOD (only current tenant):
meetings = scoped_query(MeetingSession, db).all()

# Create with auto tenant_id
meeting = create_scoped(
    MeetingSession,
    db,
    user_id=user_id,
    fathom_recording_id=recording_id
)

# Verify resource belongs to current tenant
verify_tenant_access(meeting, raise_error=True)

# Get by ID with verification
meeting = get_scoped_by_id(MeetingSession, db, meeting_id)

# Update with verification
update_scoped(meeting, db, status='completed')

# Delete with verification
delete_scoped(meeting, db, soft_delete=True)
```

**Why This Matters**:

Without scoped queries, this happens:
```python
# SECURITY VULNERABILITY!
meetings = db.query(MeetingSession).all()
# Returns: [Tenant A meetings, Tenant B meetings, Tenant C meetings, ...]
# Tenant A can see Tenant B and C's data!
```

With scoped queries:
```python
# SECURE
meetings = scoped_query(MeetingSession, db).all()
# Returns: [Only Tenant A meetings]
# Tenant isolation enforced!
```

---

### 6. `exceptions.py` - Custom Exceptions

**Exception Hierarchy**:

```python
TenantContextError          # No tenant set in context (500)
TenantNotFoundError         # Tenant doesn't exist (403)
TenantSuspendedError        # Subscription suspended (403)
InvalidSlackRequestError    # Cannot parse request (400)
TenantAccessDeniedError     # Cross-tenant access attempt (403)
TenantCacheError            # Redis error (internal only)
```

---

## Integration Guide

### Step 1: Install Dependencies

Add to `requirements.txt`:
```
redis==5.0.1
hiredis==2.3.2
```

Install:
```bash
pip install redis hiredis
```

### Step 2: Configure Environment

Add to `.env`:
```bash
# Redis Configuration (optional, for tenant caching)
REDIS_URL=redis://localhost:6379/0
REDIS_ENABLED=true
TENANT_CACHE_TTL=300  # 5 minutes

# Slack Security
SLACK_SIGNING_SECRET=your_signing_secret_here
```

### Step 3: Register Middleware

Update `src/slack_webhook_handler.py`:

```python
from flask import Flask
from middleware import TenantMiddleware

app = Flask(__name__)

# Register tenant middleware
middleware = TenantMiddleware(app, verify_signatures=True)
middleware.register()

# Your routes here...
@app.route('/slack/commands', methods=['POST'])
def slack_commands():
    # Tenant context is automatically set by middleware
    tenant = get_current_tenant()
    # ... rest of handler
```

### Step 4: Update Database Queries

**BEFORE (single-tenant)**:
```python
def get_user_meetings(user_id):
    meetings = db.query(MeetingSession).filter(
        MeetingSession.user_id == user_id
    ).all()
    return meetings
```

**AFTER (multi-tenant)**:
```python
from middleware import scoped_query, get_current_tenant

def get_user_meetings(user_id):
    # Automatically filtered by tenant_id!
    meetings = scoped_query(MeetingSession, db).filter(
        MeetingSession.user_id == user_id
    ).all()
    return meetings
```

### Step 5: Update CRM Connections

**BEFORE (hardcoded)**:
```python
crono = CronoClient(
    public_key=os.getenv('CRONO_PUBLIC_KEY'),
    private_key=os.getenv('CRONO_API_KEY')
)
```

**AFTER (tenant-scoped)**:
```python
from middleware import get_current_tenant, scoped_query
from models import CRMConnection
from providers.factory import CRMProviderFactory

# Get tenant's CRM connection
tenant = get_current_tenant()
crm_conn = scoped_query(CRMConnection, db).filter_by(
    is_default=True
).first()

if crm_conn:
    crm_provider = CRMProviderFactory.create(
        crm_conn.provider_type,
        crm_conn.get_credentials()
    )
```

### Step 6: Add Audit Logging

```python
from middleware import get_current_tenant
from models import AuditLog

def log_meeting_processed(meeting_id):
    tenant = get_current_tenant()

    audit_log = AuditLog(
        tenant_id=tenant.id,
        event_type='meeting.processed',
        resource_type='meeting_session',
        resource_id=meeting_id,
        action='create',
        metadata={'source': 'slack_webhook'}
    )
    db.add(audit_log)
```

---

## Security

### Security Checklist

- ✅ **Slack Signature Verification**: All requests verified with HMAC-SHA256
- ✅ **Replay Attack Prevention**: Timestamp validation (5-minute window)
- ✅ **Query Scoping**: All queries automatically filtered by tenant_id
- ✅ **Soft Deletes**: Deleted tenants filtered out (deleted_at IS NULL)
- ✅ **Cross-Tenant Access Prevention**: verify_tenant_access() checks
- ✅ **Audit Logging**: All tenant access logged to audit_logs table
- ✅ **Thread Isolation**: Thread-local storage prevents context leaks

### Common Security Pitfalls

#### ❌ BAD: Direct database queries
```python
# VULNERABILITY: Returns ALL tenants' data!
meetings = db.query(MeetingSession).all()
```

#### ✅ GOOD: Scoped queries
```python
# SECURE: Only current tenant's data
meetings = scoped_query(MeetingSession, db).all()
```

#### ❌ BAD: Accepting tenant_id from user input
```python
# VULNERABILITY: User can specify any tenant_id!
tenant_id = request.args.get('tenant_id')
meetings = db.query(MeetingSession).filter_by(tenant_id=tenant_id).all()
```

#### ✅ GOOD: Using context tenant_id
```python
# SECURE: tenant_id from verified context
tenant_id = get_current_tenant_id()
meetings = db.query(MeetingSession).filter_by(tenant_id=tenant_id).all()

# BETTER: Use scoped_query
meetings = scoped_query(MeetingSession, db).all()
```

#### ❌ BAD: Loading resource without verification
```python
# VULNERABILITY: No check if resource belongs to current tenant!
meeting_id = request.args.get('meeting_id')
meeting = db.query(MeetingSession).filter_by(id=meeting_id).first()
return jsonify(meeting.to_dict())
```

#### ✅ GOOD: Verify tenant access
```python
# SECURE: Verify before using
meeting_id = request.args.get('meeting_id')
meeting = get_scoped_by_id(MeetingSession, db, meeting_id)
if not meeting:
    return jsonify({'error': 'Not found'}), 404
return jsonify(meeting.to_dict())
```

---

## Performance

### Caching Strategy

**Without Redis (Direct DB Query)**:
- First request: 50-100ms
- Subsequent requests: 50-100ms each

**With Redis Caching**:
- First request: 50-100ms (cache MISS → DB query)
- Subsequent requests: 1-2ms (cache HIT)
- Cache TTL: 5 minutes
- After TTL: 50-100ms (refresh cache)

### Performance Optimization Tips

#### 1. Warm Up Cache at Startup

```python
from middleware import preload_tenants
from database import get_db

# In application startup:
with get_db() as db:
    count = preload_tenants(db, limit=500)
    logger.info(f"Preloaded {count} tenants into cache")
```

#### 2. Use Database Connection Pooling

Already configured in `database.py`:
```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)
```

#### 3. Add Database Indexes

```sql
-- Already exists in schema
CREATE INDEX idx_tenants_slack_team_id ON tenants(slack_team_id);
CREATE INDEX idx_meeting_sessions_tenant_id ON meeting_sessions(tenant_id);
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
```

#### 4. Monitor Cache Hit Rate

```python
# Add to metrics endpoint
@app.route('/metrics')
def metrics():
    cache_stats = {
        'hits': redis.get('cache_hits'),
        'misses': redis.get('cache_misses'),
        'hit_rate': calculate_hit_rate()
    }
    return jsonify(cache_stats)
```

---

## Troubleshooting

### Issue: "TenantContextError: No tenant context is currently set"

**Cause**: Attempting to access tenant context outside of a request or in a whitelisted route.

**Solution**:
```python
# Check if tenant is set before accessing
tenant = get_current_tenant_safe()
if tenant:
    # Use tenant
    pass
else:
    # Handle missing tenant
    logger.warning("No tenant context available")
```

### Issue: "TenantNotFoundError: Tenant not found"

**Cause**: Slack workspace hasn't installed the app or tenant was deleted.

**Solution**:
1. Check database: `SELECT * FROM tenants WHERE slack_team_id = 'T...'`
2. Verify app is installed in workspace
3. Check if tenant was soft-deleted: `deleted_at IS NOT NULL`

### Issue: "TenantSuspendedError: Subscription suspended"

**Cause**: Tenant's subscription is not active.

**Solution**:
1. Check subscription status: `SELECT subscription_status FROM tenants WHERE ...`
2. Verify payment/billing
3. Reactivate: `UPDATE tenants SET subscription_status = 'active' WHERE ...`

### Issue: Queries returning data from wrong tenant

**Cause**: Not using scoped_query() or verify_tenant_access().

**Solution**:
```python
# Find all direct queries and replace with scoped versions
# Bad:
meetings = db.query(MeetingSession).all()

# Good:
meetings = scoped_query(MeetingSession, db).all()
```

### Issue: Cache not working (Redis errors)

**Cause**: Redis not running or connection failed.

**Solution**:
1. Check Redis: `redis-cli ping`
2. Verify REDIS_URL in .env
3. Check Redis logs: `tail -f /var/log/redis/redis-server.log`
4. Disable Redis if unavailable: `REDIS_ENABLED=false`

### Debugging Tips

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or just for middleware:
logging.getLogger('middleware').setLevel(logging.DEBUG)
```

Check tenant context:
```python
from middleware import get_current_tenant_safe

tenant = get_current_tenant_safe()
print(f"Current tenant: {tenant}")
```

Monitor database queries:
```python
# In database.py
engine = create_engine(
    DATABASE_URL,
    echo=True  # Log all SQL queries
)
```

---

## Migration Guide

### Phase 1: Preparation (No Code Changes)

1. **Backup database**:
   ```bash
   pg_dump slack_fathom_crono > backup.sql
   ```

2. **Install Redis** (optional but recommended):
   ```bash
   # Mac
   brew install redis
   brew services start redis

   # Ubuntu
   sudo apt install redis-server
   sudo systemctl start redis
   ```

3. **Update environment**:
   ```bash
   cp .env .env.backup
   # Add Redis config to .env
   ```

### Phase 2: Install Middleware (Non-Breaking)

1. **Install dependencies**:
   ```bash
   pip install redis hiredis
   ```

2. **Import middleware** in `slack_webhook_handler.py`:
   ```python
   from middleware import TenantMiddleware
   # Don't register yet - just test import
   ```

3. **Run tests**:
   ```bash
   python src/test_tenant_middleware.py
   ```

### Phase 3: Register Middleware (Breaking Change)

**⚠️ This step requires all tenants to use the new system**

1. **Register middleware**:
   ```python
   middleware = TenantMiddleware(app)
   middleware.register()
   ```

2. **Deploy to staging**:
   ```bash
   git checkout -b feature/tenant-middleware
   git add .
   git commit -m "Add tenant middleware"
   git push origin feature/tenant-middleware
   # Deploy to staging environment
   ```

3. **Test with real Slack requests**:
   - Send slash command
   - Click buttons
   - Verify logs show tenant context

4. **Monitor for errors**:
   ```bash
   tail -f logs/app.log | grep "ERROR"
   ```

### Phase 4: Update Queries (Gradual)

Update each handler file one at a time:

```python
# File: handle_create_crono_note()

# BEFORE:
crm_type = os.getenv('CRM_PROVIDER', 'crono')

# AFTER:
from middleware import get_current_tenant, scoped_query
tenant = get_current_tenant()
crm_conn = scoped_query(CRMConnection, db).filter_by(is_default=True).first()
```

Test each change:
```bash
# Test specific functionality
python -m pytest tests/test_crono_integration.py
```

### Phase 5: Deploy to Production

1. **Final staging verification**:
   - Test all features
   - Check logs for errors
   - Verify performance

2. **Scheduled deployment**:
   ```bash
   # Off-peak hours
   git checkout main
   git merge feature/tenant-middleware
   git push origin main
   # Trigger production deployment
   ```

3. **Monitor closely**:
   - Watch error rates
   - Check response times
   - Verify cache hit rates

4. **Rollback plan**:
   ```bash
   # If issues arise:
   git revert HEAD
   git push origin main
   # Redeploy previous version
   ```

---

## Additional Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [Slack API Documentation](https://api.slack.com/)
- [Redis Documentation](https://redis.io/documentation)
- [SQLAlchemy Multi-tenancy](https://docs.sqlalchemy.org/en/14/core/connections.html)

---

**Questions or Issues?**

Open an issue on GitHub or contact the development team.

**Last Updated**: 2025-11-28
**Version**: 1.0.0
