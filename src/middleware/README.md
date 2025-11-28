# Tenant Context Middleware

Multi-tenant isolation middleware for Flask applications handling Slack webhooks.

## Overview

This middleware system ensures complete data separation between Slack workspaces (tenants) in a multi-tenant SaaS architecture. It automatically:

- Extracts tenant information from every Slack webhook
- Loads tenant from database with Redis caching
- Sets tenant in thread-local context for request lifecycle
- Provides helpers that scope all database queries to the current tenant
- Verifies Slack signatures for security
- Cleans up context after request completion

## Quick Start

### 1. Install Dependencies

```bash
pip install redis hiredis
```

### 2. Configure Environment

```bash
# .env
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
SLACK_SIGNING_SECRET=your_signing_secret
```

### 3. Register Middleware

```python
from flask import Flask
from middleware import TenantMiddleware

app = Flask(__name__)
middleware = TenantMiddleware(app)
middleware.register()
```

### 4. Use in Handlers

```python
from middleware import get_current_tenant, scoped_query
from models import MeetingSession

@app.route('/api/meetings')
def list_meetings():
    # Tenant context automatically set by middleware
    tenant = get_current_tenant()

    # All queries automatically scoped to tenant
    meetings = scoped_query(MeetingSession, db).all()

    return jsonify([m.to_dict() for m in meetings])
```

## Architecture

```
Slack Webhook
    ↓
Flask before_request
    ↓
1. Extract team_id from request
2. Verify Slack signature
3. Load tenant from cache/DB
4. Set tenant in thread-local context
    ↓
Request Handler
    ↓
- get_current_tenant() → Access tenant
- scoped_query() → Auto-filtered queries
- create_scoped() → Auto-add tenant_id
    ↓
Flask after_request
    ↓
Clear tenant context
```

## Components

### `tenant_context.py`
Thread-local context manager for storing current tenant.

```python
from middleware import (
    set_current_tenant,
    get_current_tenant,
    get_current_tenant_id,
    clear_tenant_context,
    tenant_context,
    require_tenant
)
```

### `slack_parser.py`
Parse tenant ID from various Slack webhook formats.

```python
from middleware import (
    extract_tenant_id_from_request,
    verify_slack_signature
)
```

### `tenant_loader.py`
Load tenant from database with Redis caching.

```python
from middleware import (
    load_tenant_by_slack_id,
    get_or_create_tenant,
    clear_tenant_cache
)
```

### `flask_middleware.py`
Flask integration (before_request/after_request handlers).

```python
from middleware import TenantMiddleware
```

### `query_helpers.py`
Tenant-scoped database query utilities.

```python
from middleware import (
    scoped_query,
    create_scoped,
    verify_tenant_access,
    get_scoped_by_id
)
```

### `exceptions.py`
Custom exception classes.

```python
from middleware import (
    TenantContextError,
    TenantNotFoundError,
    TenantSuspendedError,
    InvalidSlackRequestError,
    TenantAccessDeniedError
)
```

## Security Features

- **Slack Signature Verification**: HMAC-SHA256 validation on all requests
- **Replay Attack Prevention**: Timestamp validation (5-minute window)
- **Query Scoping**: Automatic tenant_id filtering on all queries
- **Cross-Tenant Protection**: verify_tenant_access() prevents data leaks
- **Audit Logging**: All tenant access logged to audit_logs table
- **Thread Isolation**: Thread-local storage prevents context contamination

## Performance

### Without Redis
- Every request: 50-100ms (DB query)

### With Redis
- Cache HIT: 1-2ms
- Cache MISS: 50-100ms (DB query + cache)
- TTL: 5 minutes (configurable)

### Optimization Tips

1. Enable Redis caching: `REDIS_ENABLED=true`
2. Warm up cache at startup: `preload_tenants(db, limit=500)`
3. Use database indexes (already in schema)
4. Monitor cache hit rate

## Common Usage Patterns

### Get Current Tenant

```python
from middleware import get_current_tenant

tenant = get_current_tenant()
print(f"Workspace: {tenant.slack_team_name}")
```

### Query with Tenant Scoping

```python
from middleware import scoped_query

# Automatically filtered by tenant_id
meetings = scoped_query(MeetingSession, db).filter(
    MeetingSession.created_at > last_week
).all()
```

### Create with Auto Tenant ID

```python
from middleware import create_scoped

meeting = create_scoped(
    MeetingSession,
    db,
    user_id=user_id,
    meeting_title="Client Call"
)
db.add(meeting)
db.commit()
```

### Verify Resource Access

```python
from middleware import verify_tenant_access

meeting = db.query(MeetingSession).filter_by(id=meeting_id).first()
verify_tenant_access(meeting, raise_error=True)
```

### Background Threads

```python
from middleware import get_current_tenant, set_current_tenant, clear_tenant_context

# Capture tenant before thread
current_tenant = get_current_tenant()

def background_task():
    set_current_tenant(current_tenant)
    try:
        # Do work
        process_meeting()
    finally:
        clear_tenant_context()

thread = threading.Thread(target=background_task)
thread.start()
```

## Testing

Run the comprehensive test suite:

```bash
python src/test_tenant_middleware.py
python src/test_tenant_middleware.py --verbose
python src/test_tenant_middleware.py --skip-redis
```

Tests cover:
- Thread-local context isolation
- Slack request parsing (all formats)
- Tenant loading from database/cache
- Query scoping enforcement
- Error handling
- Concurrent request simulation

## Documentation

- **Full Documentation**: `/docs/TENANT_MIDDLEWARE.md`
- **Integration Guide**: `/docs/INTEGRATION_EXAMPLE.md`
- **Quick Reference**: `/docs/TENANT_MIDDLEWARE_QUICK_REF.md`

## Error Handling

### TenantContextError
No tenant set in context.

```python
try:
    tenant = get_current_tenant()
except TenantContextError:
    # Handle missing tenant
    return jsonify({'error': 'Unauthorized'}), 401
```

### TenantNotFoundError
Tenant doesn't exist in database.

```python
try:
    tenant = load_tenant_by_slack_id(team_id, db)
except TenantNotFoundError:
    return jsonify({'error': 'Workspace not installed'}), 403
```

### TenantSuspendedError
Subscription is not active.

```python
try:
    tenant = load_tenant_by_slack_id(team_id, db)
except TenantSuspendedError:
    return jsonify({'error': 'Subscription suspended'}), 403
```

## Security Best Practices

### ✅ DO

- Use `scoped_query()` for all database queries
- Use `create_scoped()` to create records
- Use `verify_tenant_access()` for user-provided IDs
- Use `get_current_tenant_id()` instead of accepting tenant_id from input
- Set tenant context in background threads

### ❌ DON'T

- Use `db.query()` directly (returns all tenants' data)
- Accept `tenant_id` from user input
- Forget to set tenant context in background threads
- Skip `verify_tenant_access()` checks
- Disable signature verification in production

## Troubleshooting

### "TenantContextError: No tenant context"
- Ensure middleware is registered: `middleware.register()`
- Check if route is whitelisted
- Verify request has valid Slack signature

### "TenantNotFoundError: Tenant not found"
- Check database: `SELECT * FROM tenants WHERE slack_team_id = 'T...'`
- Verify app is installed in workspace
- Check if tenant was soft-deleted

### "Redis connection failed"
- Verify Redis is running: `redis-cli ping`
- Check REDIS_URL in .env
- Middleware will work without Redis (direct DB queries)

### Debug Mode

```python
import logging
logging.getLogger('middleware').setLevel(logging.DEBUG)
```

## Version

**Version**: 1.0.0
**Last Updated**: 2025-11-28

## Support

For questions or issues:
1. Check documentation: `/docs/TENANT_MIDDLEWARE.md`
2. Run test suite: `python src/test_tenant_middleware.py`
3. Enable debug logging
4. Open GitHub issue with logs
