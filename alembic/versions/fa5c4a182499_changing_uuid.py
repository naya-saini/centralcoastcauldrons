"""changing uuid

Revision ID: fa5c4a182499
Revises: d98c0680c287
Create Date: 2026-09-27 22:32:03.722516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa5c4a182499'
down_revision: Union[str, None] = 'd98c0680c287'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        ALTER TABLE processed_requests
        ALTER COLUMN order_id TYPE TEXT
        USING order_id::TEXT;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        ALTER TABLE processed_requests
        ALTER COLUMN order_id TYPE UUID
        USING order_id::UUID;
    """)
