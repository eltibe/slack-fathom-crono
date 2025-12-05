"""Add Google OAuth fields to user_settings

Revision ID: 20251205_0100
Revises: 20251205_0001_add_crono_public_private_keys
Create Date: 2025-12-05 01:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251205_0100'
down_revision = 'dd7f62194fd8'
branch_labels = None
depends_on = None


def upgrade():
    # Add new Google OAuth columns to user_settings table
    op.add_column('user_settings',
        sa.Column('google_email', sa.String(255), nullable=True,
                  comment='Google account email address'))

    op.add_column('user_settings',
        sa.Column('google_access_token', sa.Text(), nullable=True,
                  comment='Google OAuth access token (expires hourly)'))

    op.add_column('user_settings',
        sa.Column('google_refresh_token', sa.Text(), nullable=True,
                  comment='Google OAuth refresh token (long-lived)'))

    op.add_column('user_settings',
        sa.Column('google_token_expiry', sa.DateTime(timezone=True), nullable=True,
                  comment='Expiry time for Google access token'))

    op.add_column('user_settings',
        sa.Column('google_calendar_enabled', sa.Boolean(), server_default='true', nullable=False,
                  comment='Whether Google Calendar integration is enabled'))

    op.add_column('user_settings',
        sa.Column('google_gmail_enabled', sa.Boolean(), server_default='true', nullable=False,
                  comment='Whether Gmail integration is enabled'))


def downgrade():
    # Remove Google OAuth columns
    op.drop_column('user_settings', 'google_gmail_enabled')
    op.drop_column('user_settings', 'google_calendar_enabled')
    op.drop_column('user_settings', 'google_token_expiry')
    op.drop_column('user_settings', 'google_refresh_token')
    op.drop_column('user_settings', 'google_access_token')
    op.drop_column('user_settings', 'google_email')
