# Database Models

SQLAlchemy ORM models for Slack Fathom Crono multi-tenant application.

## Models Overview

| Model | File | Description |
|-------|------|-------------|
| `BaseModel` | `base.py` | Abstract base with UUID PKs, timestamps, soft deletes |
| `Tenant` | `tenant.py` | Slack workspaces (root of tenant hierarchy) |
| `User` | `user.py` | Slack users within workspaces |
| `CRMConnection` | `crm_connection.py` | CRM provider integrations |
| `MeetingSession` | `meeting_session.py` | Meeting processing history |
| `AccountMapping` | `account_mapping.py` | Domain to CRM account mappings |
| `AuditLog` | `audit_log.py` | Immutable security audit trail |
| `APIRateLimit` | `api_rate_limit.py` | Rate limiting per tenant |

## Quick Usage

```python
from src.database import get_db
from src.models import Tenant, User, CRMConnection

# Create a tenant
with get_db() as db:
    tenant = Tenant(
        slack_team_id="T0123456789",
        slack_team_name="My Company",
        plan_tier="pro"
    )
    db.add(tenant)
    # Commit happens automatically

# Query tenant
with get_db() as db:
    tenant = Tenant.get_by_slack_team_id(db, "T0123456789")
    print(f"Found: {tenant.slack_team_name}")
```

## Common Patterns

### Tenant Isolation
Always filter by `tenant_id`:

```python
with get_db() as db:
    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id)  # Required!
        .all()
    )
```

### Soft Deletes
```python
with get_db() as db:
    user = User.get_by_id(db, user_id)
    user.soft_delete()
    # User still in DB but excluded from queries
```

### Relationships
```python
with get_db() as db:
    tenant = Tenant.get_by_id(db, tenant_id)
    print(f"Users: {len(tenant.users)}")
    print(f"CRM Connections: {len(tenant.crm_connections)}")
```

## Documentation

- **Full Implementation Guide**: `/docs/DATABASE_IMPLEMENTATION.md`
- **Schema Design**: `/docs/DATABASE_SCHEMA.md`
- **Summary**: `/docs/DATABASE_SUMMARY.md`

## Testing

```bash
cd src
python test_database.py
```

## Model Inheritance

All models inherit from `BaseModel`:
- UUID primary key (`id`)
- Timestamps (`created_at`, `updated_at`)
- Soft delete support (`deleted_at`)
- Common methods (`get_by_id()`, `soft_delete()`, `to_dict()`)
