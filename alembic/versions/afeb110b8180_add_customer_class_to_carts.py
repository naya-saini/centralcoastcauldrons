"""add customer class to carts

Revision ID: afeb110b8180
Revises: 6dc6a022b566
Create Date: 2026-09-16 08:31:18.789801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'afeb110b8180'
down_revision: Union[str, None] = '6dc6a022b566'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
