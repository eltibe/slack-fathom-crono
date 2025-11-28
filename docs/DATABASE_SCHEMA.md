# Multi-Tenant Database Schema Design

## Overview

This database schema supports a multi-tenant SaaS architecture where each Slack workspace is an isolated tenant with its own CRM integrations, users, and meeting data.

## Design Principles

1. **Tenant Isolation**: All user data partitioned by `tenant_id` (Slack workspace ID)
2. **Multi-CRM Support**: Each tenant can connect multiple CRM providers (Crono, HubSpot, Salesforce)
3. **Security First**: Encrypted credentials stored in AWS Secrets Manager (only reference IDs in DB)
4. **Audit Trail**: All critical operations logged for compliance
5. **Scalability**: Indexed for fast queries, designed for horizontal scaling

## Technology Stack

- **Database**: PostgreSQL 15+ (RDS with Multi-AZ)
- **ORM**: SQLAlchemy 2.0 with Alembic migrations
- **Encryption**: AWS KMS for secrets, bcrypt for passwords
- **Connection Pool**: PgBouncer for connection management

---

## Schema Tables

### 1. `tenants` - Slack Workspaces

Each Slack workspace is a tenant with isolated data.

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Slack workspace identification
    slack_team_id VARCHAR(20) UNIQUE NOT NULL,  -- Slack Team ID (T0123456789)
    slack_team_name VARCHAR(255) NOT NULL,      -- Workspace display name
    slack_team_domain VARCHAR(255),             -- workspace.slack.com

    -- Subscription and billing
    plan_tier VARCHAR(50) NOT NULL DEFAULT 'free',  -- free, starter, pro, enterprise
    subscription_status VARCHAR(50) DEFAULT 'active',  -- active, suspended, cancelled
    trial_ends_at TIMESTAMP WITH TIME ZONE,

    -- Slack app installation
    slack_bot_token_secret_id VARCHAR(255),     -- AWS Secrets Manager ID
    slack_app_id VARCHAR(20),
    installed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    installed_by_user_id VARCHAR(20),           -- Slack user who installed

    -- Settings
    default_crm_provider VARCHAR(50),           -- crono, hubspot, salesforce
    timezone VARCHAR(50) DEFAULT 'UTC',
    locale VARCHAR(10) DEFAULT 'en',

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE,        -- Soft delete

    CONSTRAINT valid_plan_tier CHECK (plan_tier IN ('free', 'starter', 'pro', 'enterprise')),
    CONSTRAINT valid_subscription_status CHECK (subscription_status IN ('active', 'trial', 'suspended', 'cancelled'))
);

CREATE INDEX idx_tenants_slack_team_id ON tenants(slack_team_id);
CREATE INDEX idx_tenants_subscription_status ON tenants(subscription_status) WHERE deleted_at IS NULL;
```

### 2. `users` - Slack Users

Users within each tenant workspace.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Slack user identification
    slack_user_id VARCHAR(20) NOT NULL,         -- Slack User ID (U0123456789)
    slack_username VARCHAR(255),
    slack_email VARCHAR(255),
    slack_real_name VARCHAR(255),

    -- User preferences
    preferred_language VARCHAR(10) DEFAULT 'en',
    notification_settings JSONB DEFAULT '{"email_drafts": true, "calendar_events": true}',

    -- Role and permissions
    role VARCHAR(50) DEFAULT 'member',          -- admin, member
    is_active BOOLEAN DEFAULT true,

    -- Metadata
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    UNIQUE(tenant_id, slack_user_id),
    CONSTRAINT valid_role CHECK (role IN ('admin', 'member'))
);

CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_slack_user_id ON users(tenant_id, slack_user_id);
CREATE INDEX idx_users_last_active ON users(last_active_at DESC);
```

### 3. `crm_connections` - CRM Provider Integrations

Each tenant can connect multiple CRM providers.

```sql
CREATE TABLE crm_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- CRM provider details
    provider_type VARCHAR(50) NOT NULL,         -- crono, hubspot, salesforce
    connection_name VARCHAR(255),               -- User-friendly name ("Production HubSpot")

    -- Credentials (stored in AWS Secrets Manager)
    credentials_secret_id VARCHAR(255) NOT NULL,  -- AWS Secrets Manager ARN

    -- OAuth details (for providers like HubSpot)
    oauth_access_token_secret_id VARCHAR(255),
    oauth_refresh_token_secret_id VARCHAR(255),
    oauth_expires_at TIMESTAMP WITH TIME ZONE,
    oauth_scopes TEXT[],

    -- Connection status
    status VARCHAR(50) DEFAULT 'active',        -- active, error, disconnected
    last_sync_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT,
    last_error_at TIMESTAMP WITH TIME ZONE,

    -- Configuration
    settings JSONB DEFAULT '{}',                -- Provider-specific settings
    is_default BOOLEAN DEFAULT false,           -- Default CRM for this tenant

    -- Metadata
    connected_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT valid_provider_type CHECK (provider_type IN ('crono', 'hubspot', 'salesforce', 'pipedrive')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'error', 'disconnected', 'refreshing'))
);

CREATE INDEX idx_crm_connections_tenant_id ON crm_connections(tenant_id);
CREATE INDEX idx_crm_connections_provider_type ON crm_connections(tenant_id, provider_type);
CREATE INDEX idx_crm_connections_default ON crm_connections(tenant_id) WHERE is_default = true AND deleted_at IS NULL;
CREATE INDEX idx_crm_connections_status ON crm_connections(status) WHERE deleted_at IS NULL;
```

### 4. `meeting_sessions` - Meeting Processing History

Tracks all meetings processed through the bot.

```sql
CREATE TABLE meeting_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Fathom meeting details
    fathom_recording_id VARCHAR(255) NOT NULL,
    fathom_meeting_title VARCHAR(500),
    fathom_meeting_date TIMESTAMP WITH TIME ZONE,
    fathom_duration_minutes INTEGER,
    fathom_participants TEXT[],

    -- AI processing
    transcript_language VARCHAR(10),            -- en, it, es, fr, de
    ai_summary JSONB,                           -- Structured AI output
    email_draft TEXT,
    sales_insights JSONB,

    -- CRM integration
    crm_connection_id UUID REFERENCES crm_connections(id) ON DELETE SET NULL,
    crm_account_id VARCHAR(255),                -- CRM account ID
    crm_account_name VARCHAR(255),
    crm_note_id VARCHAR(255),                   -- Created note ID in CRM
    crm_deal_ids TEXT[],                        -- Associated deal IDs

    -- Google integrations
    gmail_draft_id VARCHAR(255),
    calendar_event_id VARCHAR(255),
    calendar_event_link TEXT,

    -- Processing metadata
    processing_status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    processing_error TEXT,

    -- Actions performed
    actions_performed JSONB DEFAULT '[]',       -- ["email_draft", "calendar_event", "crm_note"]

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_processing_status CHECK (
        processing_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')
    )
);

CREATE INDEX idx_meeting_sessions_tenant_id ON meeting_sessions(tenant_id);
CREATE INDEX idx_meeting_sessions_user_id ON meeting_sessions(user_id);
CREATE INDEX idx_meeting_sessions_fathom_id ON meeting_sessions(tenant_id, fathom_recording_id);
CREATE INDEX idx_meeting_sessions_created_at ON meeting_sessions(created_at DESC);
CREATE INDEX idx_meeting_sessions_status ON meeting_sessions(processing_status) WHERE processing_status != 'completed';
```

### 5. `account_mappings` - Domain to CRM Account Mappings

Local cache of domain → CRM account mappings for faster lookups.

```sql
CREATE TABLE account_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    crm_connection_id UUID NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,

    -- Domain mapping
    email_domain VARCHAR(255) NOT NULL,         -- neuronup.com
    company_name VARCHAR(255),                  -- NeuronUP

    -- CRM account details
    crm_account_id VARCHAR(255) NOT NULL,       -- Account ID in CRM
    crm_account_name VARCHAR(255) NOT NULL,

    -- Mapping metadata
    mapping_source VARCHAR(50),                 -- manual, auto_discovered, imported
    confidence_score DECIMAL(3,2),              -- 0.00 to 1.00 (for auto-discovered)
    verified BOOLEAN DEFAULT false,             -- Manually verified by user

    -- Usage statistics
    times_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    created_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    UNIQUE(tenant_id, crm_connection_id, email_domain),
    CONSTRAINT valid_mapping_source CHECK (mapping_source IN ('manual', 'auto_discovered', 'imported'))
);

CREATE INDEX idx_account_mappings_tenant_crm ON account_mappings(tenant_id, crm_connection_id);
CREATE INDEX idx_account_mappings_domain ON account_mappings(tenant_id, email_domain);
CREATE INDEX idx_account_mappings_verified ON account_mappings(tenant_id, crm_connection_id) WHERE verified = true;
```

### 6. `audit_logs` - Security and Compliance Audit Trail

Immutable log of all critical operations.

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Event details
    event_type VARCHAR(100) NOT NULL,           -- crm.note.created, user.login, setting.changed
    event_category VARCHAR(50) NOT NULL,        -- authentication, data_access, configuration
    resource_type VARCHAR(50),                  -- meeting_session, crm_connection, user
    resource_id UUID,

    -- Event data
    action_description TEXT NOT NULL,
    ip_address INET,
    user_agent TEXT,

    -- Request/response data
    request_data JSONB,
    response_data JSONB,

    -- Outcome
    status VARCHAR(50) NOT NULL,                -- success, failure, partial
    error_message TEXT,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_event_category CHECK (
        event_category IN ('authentication', 'data_access', 'configuration', 'integration', 'security')
    ),
    CONSTRAINT valid_status CHECK (status IN ('success', 'failure', 'partial'))
);

CREATE INDEX idx_audit_logs_tenant_id ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type, created_at DESC);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
-- Partial index for failures only (security monitoring)
CREATE INDEX idx_audit_logs_failures ON audit_logs(tenant_id, created_at DESC) WHERE status = 'failure';
```

### 7. `api_rate_limits` - Rate Limiting Tracking

Track API usage for rate limiting and quota management.

```sql
CREATE TABLE api_rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Rate limit configuration
    resource_type VARCHAR(50) NOT NULL,         -- meetings_processed, api_calls, crm_writes
    limit_period VARCHAR(20) NOT NULL,          -- hourly, daily, monthly
    limit_value INTEGER NOT NULL,               -- Max allowed in period

    -- Current usage
    current_count INTEGER DEFAULT 0,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    UNIQUE(tenant_id, resource_type, period_start),
    CONSTRAINT valid_limit_period CHECK (limit_period IN ('minute', 'hourly', 'daily', 'monthly'))
);

CREATE INDEX idx_api_rate_limits_tenant_resource ON api_rate_limits(tenant_id, resource_type, period_start);
CREATE INDEX idx_api_rate_limits_period ON api_rate_limits(period_end) WHERE current_count >= limit_value;
```

---

## Relationships Diagram

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

audit_logs ──> references all tables
api_rate_limits ──> tenants
```

---

## Migration Strategy

### Phase 1: Initial Setup (Week 1)
1. Create database schema with all tables
2. Set up Alembic for migrations
3. Create SQLAlchemy ORM models
4. Write seed data scripts

### Phase 2: Data Migration (Week 2)
1. Migrate existing single-tenant data to multi-tenant schema
2. Create initial tenant for current Slack workspace
3. Migrate account_mappings.json to database
4. Test backward compatibility

### Phase 3: Application Integration (Week 3)
1. Implement tenant context middleware
2. Update all queries to include tenant_id filters
3. Implement CRM connection management
4. Test end-to-end with existing features

---

## Security Considerations

### 1. **Credential Storage**
- **NEVER** store plaintext credentials in database
- Use AWS Secrets Manager for all sensitive data
- Store only Secret ARNs/IDs in database
- Rotate secrets regularly (quarterly)

### 2. **Tenant Isolation**
- **ALL** queries MUST include `tenant_id` filter
- Use PostgreSQL Row-Level Security (RLS) policies
- Implement application-level tenant context
- Regular security audits

### 3. **Access Control**
- Role-based access control (RBAC) via `users.role`
- API keys per tenant for external access
- OAuth 2.0 for web app authentication
- JWT tokens with tenant claim

### 4. **Data Retention**
- Soft deletes for critical tables (`deleted_at`)
- Audit logs retention: 2 years minimum
- GDPR compliance: right to be forgotten
- Automated backup and point-in-time recovery

---

## Performance Optimization

### 1. **Indexing Strategy**
- All foreign keys indexed
- Composite indexes for common queries
- Partial indexes for filtered queries
- Covering indexes for hot queries

### 2. **Partitioning**
- Partition `audit_logs` by month (time-series data)
- Partition `meeting_sessions` by created_at (if > 10M rows)
- Consider tenant-based partitioning at scale

### 3. **Caching**
- Redis cache for:
  - Tenant settings (TTL: 5 minutes)
  - CRM connections (TTL: 1 minute)
  - Account mappings (TTL: 1 hour)
- Cache invalidation on updates

### 4. **Connection Pooling**
- PgBouncer for connection management
- Pool size: 20 connections per app instance
- Statement timeout: 30 seconds
- Idle timeout: 10 minutes

---

## Sample Queries

### Get all CRM connections for a tenant
```sql
SELECT
    c.id,
    c.provider_type,
    c.connection_name,
    c.is_default,
    c.status,
    c.last_sync_at
FROM crm_connections c
WHERE c.tenant_id = :tenant_id
  AND c.deleted_at IS NULL
ORDER BY c.is_default DESC, c.created_at ASC;
```

### Find account mapping with fallback
```sql
-- Try exact domain match first
SELECT crm_account_id, crm_account_name
FROM account_mappings
WHERE tenant_id = :tenant_id
  AND crm_connection_id = :crm_connection_id
  AND email_domain = :domain
ORDER BY verified DESC, times_used DESC
LIMIT 1;
```

### Get user's recent meetings
```sql
SELECT
    m.id,
    m.fathom_meeting_title,
    m.fathom_meeting_date,
    m.processing_status,
    m.crm_account_name,
    array_length(m.actions_performed, 1) as actions_count
FROM meeting_sessions m
WHERE m.user_id = :user_id
  AND m.created_at > NOW() - INTERVAL '30 days'
ORDER BY m.created_at DESC
LIMIT 50;
```

### Check rate limit
```sql
SELECT
    current_count,
    limit_value,
    (current_count >= limit_value) as is_exceeded,
    period_end
FROM api_rate_limits
WHERE tenant_id = :tenant_id
  AND resource_type = 'meetings_processed'
  AND period_start <= NOW()
  AND period_end > NOW();
```

---

## Next Steps

1. **Review & Approve**: Validate schema design with team
2. **Create ORM Models**: Implement SQLAlchemy models in `src/models/`
3. **Set Up Migrations**: Initialize Alembic and create initial migration
4. **Implement Middleware**: Tenant context middleware for request isolation
5. **Data Migration**: Migrate existing data to new schema
6. **Testing**: Comprehensive integration tests with multi-tenant scenarios

---

**Document Version**: 1.0
**Last Updated**: 2025-11-28
**Status**: 🔍 Review Required
**Author**: Claude Code (Implementation Engineer)
