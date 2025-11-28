# Tenant Middleware Quick Reference

Quick reference for common tenant middleware operations.

## Installation

```bash
pip install redis hiredis
```

Add to `.env`:
```bash
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
SLACK_SIGNING_SECRET=your_signing_secret
```

## Basic Setup

```python
from flask import Flask
from middleware import TenantMiddleware

app = Flask(__name__)
middleware = TenantMiddleware(app)
middleware.register()
```

## Common Operations

### Get Current Tenant

```python
from middleware import get_current_tenant, get_current_tenant_id

# Get full tenant object
tenant = get_current_tenant()
print(tenant.slack_team_name)

# Get just the ID
tenant_id = get_current_tenant_id()
```

### Database Queries

```python
from middleware import scoped_query, create_scoped
from models import MeetingSession

# Query (automatically filtered by tenant)
meetings = scoped_query(MeetingSession, db).all()

# Create (tenant_id auto-added)
meeting = create_scoped(
    MeetingSession,
    db,
    user_id=user_id,
    meeting_title="Client Call"
)
db.add(meeting)
db.commit()
```

### Verify Access

```python
from middleware import verify_tenant_access

# Verify resource belongs to current tenant
meeting = db.query(MeetingSession).filter_by(id=meeting_id).first()
verify_tenant_access(meeting, raise_error=True)
```

### Context Manager

```python
from middleware import tenant_context

with tenant_context(tenant):
    # All operations scoped to tenant
    process_data()
```

### Decorator

```python
from middleware import require_tenant

@require_tenant()
def my_handler():
    tenant = get_current_tenant()
    # tenant guaranteed to be set
```

## CRM Integration

```python
from middleware import get_current_tenant, scoped_query
from models import CRMConnection
from providers.factory import CRMProviderFactory

# Get tenant's CRM connection
tenant = get_current_tenant()
crm_conn = scoped_query(CRMConnection, db).filter_by(is_default=True).first()

if crm_conn:
    crm_provider = CRMProviderFactory.create(
        crm_conn.provider_type,
        crm_conn.get_credentials()
    )
```

## Background Threads

```python
from middleware import get_current_tenant, set_current_tenant, clear_tenant_context

# Capture tenant before thread
current_tenant = get_current_tenant()

def background_task():
    # Set tenant in new thread
    set_current_tenant(current_tenant)

    try:
        # Do work
        process_meeting()
    finally:
        # Clean up
        clear_tenant_context()

thread = threading.Thread(target=background_task)
thread.start()
```

## Error Handling

```python
from middleware.exceptions import (
    TenantNotFoundError,
    TenantSuspendedError,
    TenantContextError
)

try:
    tenant = get_current_tenant()
except TenantContextError:
    # No tenant set
    return jsonify({'error': 'Unauthorized'}), 401

try:
    tenant = load_tenant_by_slack_id(team_id, db)
except TenantNotFoundError:
    # Tenant doesn't exist
    return jsonify({'error': 'Not installed'}), 403
except TenantSuspendedError:
    # Subscription suspended
    return jsonify({'error': 'Suspended'}), 403
```

## Cache Operations

```python
from middleware import clear_tenant_cache

# Clear specific tenant
clear_tenant_cache("T0123456789")

# Clear all tenant cache
clear_tenant_cache()
```

## Testing

```bash
# Run full test suite
python src/test_tenant_middleware.py

# Run with verbose output
python src/test_tenant_middleware.py --verbose

# Skip Redis tests
python src/test_tenant_middleware.py --skip-redis
```

## Security Checklist

- ✅ Use `scoped_query()` instead of `db.query()`
- ✅ Use `create_scoped()` to create records
- ✅ Use `verify_tenant_access()` for user-provided IDs
- ✅ Never accept `tenant_id` from user input
- ✅ Always use `get_current_tenant_id()` for queries
- ✅ Set tenant context in background threads
- ✅ Verify Slack signatures (middleware does this)

## Common Mistakes

### ❌ DON'T: Direct query
```python
# WRONG - returns ALL tenants' data
meetings = db.query(MeetingSession).all()
```

### ✅ DO: Scoped query
```python
# CORRECT - only current tenant
meetings = scoped_query(MeetingSession, db).all()
```

### ❌ DON'T: Accept tenant_id from user
```python
# WRONG - security vulnerability
tenant_id = request.args.get('tenant_id')
meetings = db.query(MeetingSession).filter_by(tenant_id=tenant_id).all()
```

### ✅ DO: Use context tenant_id
```python
# CORRECT - tenant_id from verified context
tenant_id = get_current_tenant_id()
meetings = db.query(MeetingSession).filter_by(tenant_id=tenant_id).all()

# BETTER - use scoped_query
meetings = scoped_query(MeetingSession, db).all()
```

### ❌ DON'T: Forget to set context in threads
```python
# WRONG - thread has no tenant context
def background_task():
    tenant = get_current_tenant()  # Raises TenantContextError!
```

### ✅ DO: Pass and set tenant in threads
```python
# CORRECT - tenant context set in thread
current_tenant = get_current_tenant()

def background_task():
    set_current_tenant(current_tenant)
    try:
        tenant = get_current_tenant()  # Works!
    finally:
        clear_tenant_context()
```

## Debugging

### Enable verbose logging
```python
import logging
logging.getLogger('middleware').setLevel(logging.DEBUG)
```

### Check tenant context
```python
from middleware import get_current_tenant_safe

tenant = get_current_tenant_safe()
if tenant:
    print(f"Tenant: {tenant.slack_team_name}")
else:
    print("No tenant context")
```

### Monitor SQL queries
```python
# In database.py
engine = create_engine(
    DATABASE_URL,
    echo=True  # Log all SQL
)
```

## Performance Tips

1. **Enable Redis caching**:
   ```bash
   REDIS_ENABLED=true
   ```

2. **Warm up cache at startup**:
   ```python
   from middleware import preload_tenants
   count = preload_tenants(db, limit=500)
   ```

3. **Use database indexes** (already in schema):
   ```sql
   CREATE INDEX idx_tenants_slack_team_id ON tenants(slack_team_id);
   CREATE INDEX idx_meeting_sessions_tenant_id ON meeting_sessions(tenant_id);
   ```

4. **Monitor cache hit rate**:
   ```python
   # Add metrics to /metrics endpoint
   ```

## Resources

- Full docs: `docs/TENANT_MIDDLEWARE.md`
- Integration guide: `docs/INTEGRATION_EXAMPLE.md`
- Test suite: `src/test_tenant_middleware.py`
- Source code: `src/middleware/`

## Support

For questions or issues:
1. Check full documentation
2. Run test suite to verify setup
3. Enable debug logging
4. Open GitHub issue with logs
