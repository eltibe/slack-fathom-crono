"""Split Crono keys into public/private columns

Revision ID: add_crono_public_private_keys
Revises: 6a2601a43caf
Create Date: 2025-12-05 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_crono_public_private_keys'
down_revision: Union[str, None] = '6a2601a43caf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_settings', sa.Column('crono_public_key', sa.String(length=255), nullable=True, comment='Crono public API key'))
    op.add_column('user_settings', sa.Column('crono_private_key', sa.String(length=255), nullable=True, comment='Crono private API key'))


def downgrade() -> None:
    op.drop_column('user_settings', 'crono_private_key')
    op.drop_column('user_settings', 'crono_public_key')
