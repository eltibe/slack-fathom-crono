# Database Implementation Guide

## Overview

This document explains how to set up, configure, and use the PostgreSQL database with SQLAlchemy ORM for the Slack Fathom Crono multi-tenant application.

**Architecture**: Multi-tenant SaaS with 7 tables supporting isolated Slack workspaces, CRM integrations, meeting processing, and audit trails.

**Technology Stack**:
- PostgreSQL 15+ (production) or PostgreSQL 14+ (development)
- SQLAlchemy 2.0 (modern async-capable ORM)
- Alembic (database migrations)
- Python 3.10+

---

## Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# This installs:
# - sqlalchemy==2.0.23
# - alembic==1.13.0
# - psycopg2-binary==2.9.9
# - python-dotenv==1.0.0
```

### 2. Set Up PostgreSQL Database

**Option A: Local PostgreSQL**

```bash
# Install PostgreSQL (macOS)
brew install postgresql@15
brew services start postgresql@15

# Create database
createdb slack_fathom_crono

# Create user (optional)
psql postgres -c "CREATE USER myuser WITH PASSWORD 'mypassword';"
psql postgres -c "GRANT ALL PRIVILEGES ON DATABASE slack_fathom_crono TO myuser;"
```

**Option B: Docker PostgreSQL**

```bash
# Run PostgreSQL in Docker
docker run -d \
  --name slack-fathom-postgres \
  -e POSTGRES_DB=slack_fathom_crono \
  -e POSTGRES_USER=myuser \
  -e POSTGRES_PASSWORD=mypassword \
  -p 5432:5432 \
  postgres:15-alpine

# Verify it's running
docker ps | grep slack-fathom-postgres
```

**Option C: AWS RDS (Production)**

1. Create RDS PostgreSQL instance in AWS Console
2. Use Multi-AZ deployment for high availability
3. Enable automated backups
4. Store credentials in AWS Secrets Manager
5. Use connection string from RDS dashboard

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and update the database URL:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Database Configuration
DATABASE_URL=postgresql://myuser:mypassword@localhost:5432/slack_fathom_crono

# Connection pool settings (adjust based on load)
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600

# Debug mode (logs SQL - development only!)
DATABASE_ECHO=false
```

### 4. Run Database Migrations

```bash
# Initialize Alembic (only needed once - already done)
# alembic init alembic

# Run migrations to create all tables
alembic upgrade head

# Verify tables were created
psql slack_fathom_crono -c "\dt"
```

### 5. Test Database Setup

```bash
# Run comprehensive test suite
cd src
python test_database.py

# You should see:
# ✓ All tests passed!
```

---

## Database Schema

### Tables Overview

| Table | Purpose | Key Features |
|-------|---------|--------------|
| `tenants` | Slack workspaces | Root of tenant hierarchy, subscription management |
| `users` | Slack users | Per-tenant users with roles and preferences |
| `crm_connections` | CRM integrations | Multi-CRM support (HubSpot, Salesforce, Crono) |
| `meeting_sessions` | Meeting history | AI processing results, CRM integration tracking |
| `account_mappings` | Domain mappings | Local cache for faster CRM account lookups |
| `audit_logs` | Audit trail | Immutable security and compliance logs |
| `api_rate_limits` | Rate limiting | Token bucket rate limiting per tenant |

### Key Relationships

```
tenants (1) ──────< (M) users
   │                      │
   │                      │ created_by
   ├──< crm_connections <─┘
   │         │
   │         ├──< account_mappings
   │         │
   │         └──< meeting_sessions
   │                   │
   └──────────────────<┘

audit_logs ──> references all tables (nullable)
api_rate_limits ──> tenants
```

---

## Using the Models

### Basic CRUD Operations

```python
from src.database import get_db
from src.models import Tenant, User, CRMConnection

# CREATE
with get_db() as db:
    tenant = Tenant(
        slack_team_id="T0123456789",
        slack_team_name="My Company",
        plan_tier="pro"
    )
    db.add(tenant)
    db.flush()  # Get ID without committing

    print(f"Created tenant: {tenant.id}")

# READ
with get_db() as db:
    tenant = Tenant.get_by_slack_team_id(db, "T0123456789")
    print(f"Found tenant: {tenant.slack_team_name}")

# UPDATE
with get_db() as db:
    tenant = Tenant.get_by_slack_team_id(db, "T0123456789")
    tenant.plan_tier = "enterprise"
    # Commit happens automatically on context exit

# SOFT DELETE
with get_db() as db:
    tenant = Tenant.get_by_id(db, tenant_id)
    tenant.soft_delete()
    # Tenant is marked deleted but not removed from database
```

### Tenant Isolation Patterns

**CRITICAL**: All queries MUST filter by `tenant_id` to ensure data isolation.

```python
from src.database import get_db
from src.models import User, MeetingSession

def get_tenant_meetings(tenant_id: UUID, days: int = 30):
    """Get recent meetings for a tenant."""
    with get_db() as db:
        # ALWAYS filter by tenant_id first!
        cutoff = datetime.now() - timedelta(days=days)

        meetings = (
            db.query(MeetingSession)
            .filter(MeetingSession.tenant_id == tenant_id)  # REQUIRED
            .filter(MeetingSession.created_at >= cutoff)
            .filter(MeetingSession.deleted_at.is_(None))
            .order_by(MeetingSession.created_at.desc())
            .limit(50)
            .all()
        )

        return meetings
```

### Working with Relationships

```python
from src.database import get_db
from src.models import Tenant, User, CRMConnection

with get_db() as db:
    # Get tenant with all related data
    tenant = Tenant.get_by_slack_team_id(db, "T0123456789")

    # Access relationships (lazy loaded)
    print(f"Users: {len(tenant.users)}")
    print(f"CRM Connections: {len(tenant.crm_connections)}")

    # Create related objects
    user = User(
        tenant_id=tenant.id,
        slack_user_id="U0123456789",
        slack_email="user@company.com",
        role="admin"
    )
    db.add(user)

    crm_conn = CRMConnection(
        tenant_id=tenant.id,
        provider_type="hubspot",
        credentials_secret_id="arn:aws:secretsmanager:...",
        connected_by_user_id=user.id,
        is_default=True
    )
    db.add(crm_conn)

    # Relationships are automatically set
    assert user in tenant.users
    assert crm_conn in tenant.crm_connections
```

### Audit Logging

```python
from src.database import get_db
from src.models import AuditLog

with get_db() as db:
    # Log an event
    AuditLog.log_event(
        session=db,
        tenant_id=tenant_id,
        user_id=user_id,
        event_type="crm.note.created",
        event_category="integration",
        action_description="Created meeting note in HubSpot",
        status="success",
        resource_type="meeting_session",
        resource_id=meeting_id,
        ip_address="192.168.1.1",
        user_agent="Slack-Bot/1.0"
    )

    # Query audit logs
    recent_logs = AuditLog.get_tenant_logs(
        db,
        tenant_id=tenant_id,
        days=7,
        limit=100
    )

    # Get failures for security monitoring
    failures = AuditLog.get_recent_failures(
        db,
        tenant_id=tenant_id,
        hours=24
    )
```

### Rate Limiting

```python
from src.database import get_db
from src.models import APIRateLimit

with get_db() as db:
    # Check if request is allowed
    is_allowed, rate_limit = APIRateLimit.check_limit(
        session=db,
        tenant_id=tenant_id,
        resource_type="meetings_processed",
        limit_period="daily",
        limit_value=100
    )

    if not is_allowed:
        raise Exception(f"Rate limit exceeded: {rate_limit.current_count}/{rate_limit.limit_value}")

    # Process the meeting...

    # Increment usage counter
    success, rate_limit = APIRateLimit.increment_usage(
        session=db,
        tenant_id=tenant_id,
        resource_type="meetings_processed",
        limit_period="daily",
        limit_value=100
    )

    print(f"Usage: {rate_limit.current_count}/{rate_limit.limit_value}")
```

---

## Common Query Examples

### Get User's Recent Meetings

```python
def get_user_meetings(user_id: UUID, limit: int = 50):
    """Get recent meetings for a user."""
    with get_db() as db:
        meetings = MeetingSession.get_user_sessions(
            session=db,
            user_id=user_id,
            limit=limit,
            days=30
        )
        return meetings
```

### Find CRM Account by Email Domain

```python
def find_crm_account(tenant_id: UUID, email: str):
    """Find CRM account for an email address."""
    domain = email.split('@')[1]

    with get_db() as db:
        # Get default CRM connection
        tenant = Tenant.get_by_id(db, tenant_id)
        crm_conn = tenant.get_default_crm_connection(db)

        if not crm_conn:
            return None

        # Look up domain mapping
        mapping = AccountMapping.get_by_domain(
            session=db,
            tenant_id=tenant_id,
            crm_connection_id=crm_conn.id,
            email_domain=domain,
            verified_only=False
        )

        return mapping
```

### Get Tenant Statistics

```python
def get_tenant_stats(tenant_id: UUID):
    """Get statistics for a tenant."""
    with get_db() as db:
        tenant = Tenant.get_by_id(db, tenant_id)

        stats = {
            "users": len(tenant.users),
            "crm_connections": len(tenant.crm_connections),
            "meetings_total": db.query(MeetingSession)
                .filter(MeetingSession.tenant_id == tenant_id)
                .count(),
            "meetings_this_month": db.query(MeetingSession)
                .filter(MeetingSession.tenant_id == tenant_id)
                .filter(MeetingSession.created_at >= datetime.now() - timedelta(days=30))
                .count(),
            "account_mappings": len(tenant.account_mappings),
        }

        return stats
```

---

## Alembic Migrations

### Creating a New Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add new_field to users table"

# Manually create empty migration
alembic revision -m "Add custom index"

# Edit the generated file in alembic/versions/
# Add your upgrade() and downgrade() logic
```

### Running Migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade to specific version
alembic upgrade abc123

# Downgrade one version
alembic downgrade -1

# Show current version
alembic current

# Show migration history
alembic history
```

### Migration Best Practices

1. **Always test migrations** on a copy of production data first
2. **Write reversible migrations** (implement `downgrade()`)
3. **Use transactions** - migrations run in a transaction by default
4. **Add indexes separately** for large tables (CREATE INDEX CONCURRENTLY)
5. **Avoid data loss** - never drop columns without backup

---

## Performance Optimization

### Indexing Strategy

All critical indexes are already defined in the models. Key indexes:

- **Foreign keys**: All FK columns have indexes
- **Lookup fields**: `slack_team_id`, `slack_user_id`, `email_domain`
- **Filtering fields**: `subscription_status`, `processing_status`
- **Partial indexes**: For commonly filtered subsets (e.g., active records)

### Query Optimization Tips

```python
# BAD: N+1 query problem
tenants = db.query(Tenant).all()
for tenant in tenants:
    print(len(tenant.users))  # Each iteration hits DB

# GOOD: Use eager loading
from sqlalchemy.orm import joinedload

tenants = db.query(Tenant).options(
    joinedload(Tenant.users)
).all()
for tenant in tenants:
    print(len(tenant.users))  # No additional queries
```

### Connection Pooling

Connection pool is configured in `src/database.py`:

```python
# Default settings (adjust based on load)
DATABASE_POOL_SIZE=20        # Connections to keep open
DATABASE_MAX_OVERFLOW=10     # Extra connections when needed
DATABASE_POOL_TIMEOUT=30     # Wait time for connection (seconds)
DATABASE_POOL_RECYCLE=3600   # Recycle connections after 1 hour
```

---

## Backup and Recovery

### Backup Database

```bash
# Full database backup
pg_dump slack_fathom_crono > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed backup
pg_dump slack_fathom_crono | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Backup specific tables
pg_dump -t tenants -t users slack_fathom_crono > critical_tables_backup.sql
```

### Restore Database

```bash
# Restore from backup
psql slack_fathom_crono < backup_20251128_150000.sql

# Restore compressed backup
gunzip -c backup_20251128_150000.sql.gz | psql slack_fathom_crono
```

### AWS RDS Automated Backups

For production, use AWS RDS automated backups:

1. Enable automated backups (retention 7-30 days)
2. Set backup window to off-peak hours
3. Enable point-in-time recovery
4. Test restore process quarterly

---

## Troubleshooting

### Connection Issues

```python
# Test connection
from src.database import check_connection, get_database_info

if not check_connection():
    print("Connection failed!")
    print(get_database_info())
else:
    print("Connection successful!")
```

**Common issues**:
- Wrong DATABASE_URL format
- PostgreSQL not running
- Firewall blocking port 5432
- Wrong credentials

### Migration Issues

```bash
# Check current version
alembic current

# Show SQL without running it
alembic upgrade head --sql

# Stamp database with version (skip migration)
alembic stamp head

# Reset alembic_version table
psql slack_fathom_crono -c "DELETE FROM alembic_version;"
alembic stamp head
```

### Performance Issues

```python
# Enable SQL logging to see slow queries
import os
os.environ['DATABASE_ECHO'] = 'true'

# Use EXPLAIN to analyze queries
from sqlalchemy import text

with get_db() as db:
    result = db.execute(text("""
        EXPLAIN ANALYZE
        SELECT * FROM meeting_sessions
        WHERE tenant_id = 'xxx'
    """))
    print(result.fetchall())
```

---

## Security Best Practices

### 1. Credentials Management

- **NEVER** hardcode credentials in code
- Use AWS Secrets Manager for production
- Store only secret ARNs in database (not actual credentials)
- Rotate secrets quarterly

### 2. Tenant Isolation

- **ALWAYS** filter by `tenant_id` in queries
- Use PostgreSQL Row-Level Security (RLS) for additional protection
- Implement tenant context middleware in application
- Regular security audits for cross-tenant leaks

### 3. SQL Injection Prevention

SQLAlchemy automatically parameterizes queries:

```python
# SAFE: SQLAlchemy parameterizes automatically
user_id = request.args.get('user_id')
user = db.query(User).filter(User.id == user_id).first()

# UNSAFE: Don't use raw SQL with string formatting
query = f"SELECT * FROM users WHERE id = '{user_id}'"  # VULNERABLE!
```

### 4. Audit Logging

- Log all critical operations (CRM writes, config changes)
- Never log sensitive data (passwords, tokens, PII)
- Retain audit logs for 2+ years for compliance
- Monitor for suspicious patterns (repeated failures)

---

## Testing

### Run Test Suite

```bash
cd src
python test_database.py
```

Tests cover:
- Database connection
- Table creation
- CRUD operations on all models
- Relationships
- Tenant isolation
- Soft delete functionality
- Rate limiting
- Audit logging

### Manual Testing

```python
# Interactive testing in Python shell
from src.database import get_db
from src.models import *

with get_db() as db:
    # Create test tenant
    tenant = Tenant(
        slack_team_id="T_TEST_001",
        slack_team_name="Test Workspace",
        plan_tier="pro"
    )
    db.add(tenant)
    db.flush()

    print(f"Created tenant: {tenant.id}")

    # Test queries
    found = Tenant.get_by_slack_team_id(db, "T_TEST_001")
    print(f"Found: {found.slack_team_name}")

    # Rollback (don't save test data)
    db.rollback()
```

---

## Production Deployment Checklist

- [ ] PostgreSQL 15+ running with Multi-AZ (RDS)
- [ ] Database credentials stored in AWS Secrets Manager
- [ ] Connection pooling configured (PgBouncer recommended)
- [ ] Alembic migrations run successfully
- [ ] Automated backups enabled (7+ day retention)
- [ ] Monitoring set up (CloudWatch, Datadog, etc.)
- [ ] SSL/TLS encryption for connections enabled
- [ ] Row-Level Security (RLS) policies configured
- [ ] Test suite passes in production-like environment
- [ ] Disaster recovery plan documented
- [ ] Runbook for common operations created

---

## Additional Resources

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Database Schema Design](./DATABASE_SCHEMA.md) - Full schema specification

---

**Document Version**: 1.0
**Last Updated**: 2025-11-28
**Status**: ✅ Production Ready
**Author**: Claude Code (Implementation Engineer)
