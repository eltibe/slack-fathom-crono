"""Initial schema with all 7 tables for multi-tenant architecture

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-11-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables for multi-tenant architecture."""

    # -------------------------------------------------------------------------
    # 1. CREATE TENANTS TABLE
    # -------------------------------------------------------------------------
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slack_team_id', sa.String(20), nullable=False, unique=True),
        sa.Column('slack_team_name', sa.String(255), nullable=False),
        sa.Column('slack_team_domain', sa.String(255), nullable=True),
        sa.Column('plan_tier', sa.String(50), nullable=False, server_default='free'),
        sa.Column('subscription_status', sa.String(50), nullable=True, server_default='active'),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('slack_bot_token_secret_id', sa.String(255), nullable=True),
        sa.Column('slack_app_id', sa.String(20), nullable=True),
        sa.Column('installed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('installed_by_user_id', sa.String(20), nullable=True),
        sa.Column('default_crm_provider', sa.String(50), nullable=True),
        sa.Column('timezone', sa.String(50), nullable=False, server_default='UTC'),
        sa.Column('locale', sa.String(10), nullable=False, server_default='en'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("plan_tier IN ('free', 'starter', 'pro', 'enterprise')", name='valid_plan_tier'),
        sa.CheckConstraint("subscription_status IN ('active', 'trial', 'suspended', 'cancelled')", name='valid_subscription_status'),
    )

    op.create_index('idx_tenants_slack_team_id', 'tenants', ['slack_team_id'])
    op.create_index('idx_tenants_subscription_status', 'tenants', ['subscription_status'],
                   postgresql_where=sa.text('deleted_at IS NULL'))

    # -------------------------------------------------------------------------
    # 2. CREATE USERS TABLE
    # -------------------------------------------------------------------------
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slack_user_id', sa.String(20), nullable=False),
        sa.Column('slack_username', sa.String(255), nullable=True),
        sa.Column('slack_email', sa.String(255), nullable=True),
        sa.Column('slack_real_name', sa.String(255), nullable=True),
        sa.Column('preferred_language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('notification_settings', postgresql.JSONB, nullable=False,
                 server_default='{"email_drafts": true, "calendar_events": true}'),
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'slack_user_id', name='uq_user_tenant_slack_id'),
        sa.CheckConstraint("role IN ('admin', 'member')", name='valid_role'),
    )

    op.create_index('idx_users_tenant_id', 'users', ['tenant_id'])
    op.create_index('idx_users_slack_user_id', 'users', ['tenant_id', 'slack_user_id'])
    op.create_index('idx_users_last_active', 'users', ['last_active_at'])

    # -------------------------------------------------------------------------
    # 3. CREATE CRM_CONNECTIONS TABLE
    # -------------------------------------------------------------------------
    op.create_table(
        'crm_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('connection_name', sa.String(255), nullable=True),
        sa.Column('credentials_secret_id', sa.String(255), nullable=False),
        sa.Column('oauth_access_token_secret_id', sa.String(255), nullable=True),
        sa.Column('oauth_refresh_token_secret_id', sa.String(255), nullable=True),
        sa.Column('oauth_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('oauth_scopes', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('settings', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('connected_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connected_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.CheckConstraint("provider_type IN ('crono', 'hubspot', 'salesforce', 'pipedrive')", name='valid_provider_type'),
        sa.CheckConstraint("status IN ('active', 'error', 'disconnected', 'refreshing')", name='valid_status'),
    )

    op.create_index('idx_crm_connections_tenant_id', 'crm_connections', ['tenant_id'])
    op.create_index('idx_crm_connections_provider_type', 'crm_connections', ['tenant_id', 'provider_type'])
    op.create_index('idx_crm_connections_default', 'crm_connections', ['tenant_id'],
                   postgresql_where=sa.text('is_default = true AND deleted_at IS NULL'))
    op.create_index('idx_crm_connections_status', 'crm_connections', ['status'],
                   postgresql_where=sa.text('deleted_at IS NULL'))

    # -------------------------------------------------------------------------
    # 4. CREATE MEETING_SESSIONS TABLE
    # -------------------------------------------------------------------------
    op.create_table(
        'meeting_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fathom_recording_id', sa.String(255), nullable=False),
        sa.Column('fathom_meeting_title', sa.String(500), nullable=True),
        sa.Column('fathom_meeting_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fathom_duration_minutes', sa.Integer, nullable=True),
        sa.Column('fathom_participants', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('transcript_language', sa.String(10), nullable=True),
        sa.Column('ai_summary', postgresql.JSONB, nullable=True),
        sa.Column('email_draft', sa.Text, nullable=True),
        sa.Column('sales_insights', postgresql.JSONB, nullable=True),
        sa.Column('crm_connection_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('crm_account_id', sa.String(255), nullable=True),
        sa.Column('crm_account_name', sa.String(255), nullable=True),
        sa.Column('crm_note_id', sa.String(255), nullable=True),
        sa.Column('crm_deal_ids', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('gmail_draft_id', sa.String(255), nullable=True),
        sa.Column('calendar_event_id', sa.String(255), nullable=True),
        sa.Column('calendar_event_link', sa.Text, nullable=True),
        sa.Column('processing_status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_error', sa.Text, nullable=True),
        sa.Column('actions_performed', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['crm_connection_id'], ['crm_connections.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "processing_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name='valid_processing_status'
        ),
    )

    op.create_index('idx_meeting_sessions_tenant_id', 'meeting_sessions', ['tenant_id'])
    op.create_index('idx_meeting_sessions_user_id', 'meeting_sessions', ['user_id'])
    op.create_index('idx_meeting_sessions_fathom_id', 'meeting_sessions', ['tenant_id', 'fathom_recording_id'])
    op.create_index('idx_meeting_sessions_created_at', 'meeting_sessions', ['created_at'])
    op.create_index('idx_meeting_sessions_status', 'meeting_sessions', ['processing_status'],
                   postgresql_where=sa.text("processing_status != 'completed'"))

    # -------------------------------------------------------------------------
    # 5. CREATE ACCOUNT_MAPPINGS TABLE
    # -------------------------------------------------------------------------
    op.create_table(
        'account_mappings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('crm_connection_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email_domain', sa.String(255), nullable=False),
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('crm_account_id', sa.String(255), nullable=False),
        sa.Column('crm_account_name', sa.String(255), nullable=False),
        sa.Column('mapping_source', sa.String(50), nullable=True),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('verified', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('times_used', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['crm_connection_id'], ['crm_connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('tenant_id', 'crm_connection_id', 'email_domain',
                          name='uq_account_mapping_tenant_crm_domain'),
        sa.CheckConstraint("mapping_source IN ('manual', 'auto_discovered', 'imported')", name='valid_mapping_source'),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0.00 AND confidence_score <= 1.00)",
            name='valid_confidence_score'
        ),
    )

    op.create_index('idx_account_mappings_tenant_crm', 'account_mappings', ['tenant_id', 'crm_connection_id'])
    op.create_index('idx_account_mappings_domain', 'account_mappings', ['tenant_id', 'email_domain'])
    op.create_index('idx_account_mappings_verified', 'account_mappings', ['tenant_id', 'crm_connection_id'],
                   postgresql_where=sa.text('verified = true'))

    # -------------------------------------------------------------------------
    # 6. CREATE AUDIT_LOGS TABLE
    # -------------------------------------------------------------------------
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('event_category', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_description', sa.Text, nullable=False),
        sa.Column('ip_address', postgresql.INET, nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('request_data', postgresql.JSONB, nullable=True),
        sa.Column('response_data', postgresql.JSONB, nullable=True),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "event_category IN ('authentication', 'data_access', 'configuration', 'integration', 'security')",
            name='valid_event_category'
        ),
        sa.CheckConstraint("status IN ('success', 'failure', 'partial')", name='valid_status'),
    )

    op.create_index('idx_audit_logs_tenant_created', 'audit_logs', ['tenant_id', 'created_at'])
    op.create_index('idx_audit_logs_user_created', 'audit_logs', ['user_id', 'created_at'])
    op.create_index('idx_audit_logs_event_type', 'audit_logs', ['event_type', 'created_at'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_logs_failures', 'audit_logs', ['tenant_id', 'created_at'],
                   postgresql_where=sa.text("status = 'failure'"))

    # -------------------------------------------------------------------------
    # 7. CREATE API_RATE_LIMITS TABLE
    # -------------------------------------------------------------------------
    op.create_table(
        'api_rate_limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('limit_period', sa.String(20), nullable=False),
        sa.Column('limit_value', sa.Integer, nullable=False),
        sa.Column('current_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'resource_type', 'period_start',
                          name='uq_rate_limit_tenant_resource_period'),
        sa.CheckConstraint("limit_period IN ('minute', 'hourly', 'daily', 'monthly')", name='valid_limit_period'),
        sa.CheckConstraint("limit_value > 0", name='positive_limit_value'),
        sa.CheckConstraint("current_count >= 0", name='non_negative_current_count'),
    )

    op.create_index('idx_api_rate_limits_tenant_resource', 'api_rate_limits',
                   ['tenant_id', 'resource_type', 'period_start'])
    op.create_index('idx_api_rate_limits_period', 'api_rate_limits', ['period_end'],
                   postgresql_where=sa.text('current_count >= limit_value'))


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('api_rate_limits')
    op.drop_table('audit_logs')
    op.drop_table('account_mappings')
    op.drop_table('meeting_sessions')
    op.drop_table('crm_connections')
    op.drop_table('users')
    op.drop_table('tenants')
